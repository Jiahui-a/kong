"""将芯片测试文件夹名称与 database 记录匹配（按项目上下文）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .database import ChipRecord, Database, normalize_project_name, resolve_project_name

# 匹配优先级（数值越小越优先）
_PRIORITY = {
    "designator_exact": 10,
    "part_number_exact": 15,
    "model_exact": 20,
    "model_designator_exact": 30,
    "designator_model_exact": 30,
    "token_set": 40,
    "partial_field": 50,
}


@dataclass(frozen=True)
class FolderMatch:
    """文件夹与 database 记录的匹配结果。"""

    folder_path: Path
    project_name: str
    record: ChipRecord
    match_type: str
    parsed_folder_name: str
    matched_designator: str = ""

    @property
    def target_name(self) -> str:
        """公盘目标文件夹名：``[料号_型号]``。"""
        return self.record.target_name(self.project_name, self.matched_designator)


def parse_chip_folder_name(folder_name: str) -> str:
    """解析芯片测试文件夹名，提取 [] 内的内容。

    支持 [] 后还有后缀的命名，例如 ``[Car_Interface]_02`` → ``Car_Interface``。
    """
    name = folder_name.strip()
    bracket_match = re.search(r"\[(.*?)\]", name, flags=re.DOTALL)
    if bracket_match:
        return bracket_match.group(1).strip()
    return name


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value).upper()


def _tokenize(value: str) -> frozenset[str]:
    parts = re.split(r"[\s_\-]+", value.strip())
    tokens = {_normalize_text(part) for part in parts if part.strip()}
    return frozenset(tokens)


def _default_designator(designators: list[str]) -> str:
    if len(designators) == 1:
        return designators[0]
    return ""


def _build_field_terms(
    record: ChipRecord,
    project_name: str,
) -> list[tuple[str, str, str]]:
    """生成可单独匹配的字段项：(比对文本, 匹配类型, 关联位号)。"""
    designators = record.designators_in(project_name)
    if not designators:
        return []

    terms: list[tuple[str, str, str]] = []
    for designator in designators:
        terms.append((designator, "designator_exact", designator))

    if record.part_number:
        terms.append(
            (record.part_number, "part_number_exact", _default_designator(designators))
        )

    if record.model:
        terms.append((record.model, "model_exact", _default_designator(designators)))

    if record.model:
        for designator in designators:
            terms.extend(
                [
                    (f"{record.model} {designator}", "model_designator_exact", designator),
                    (f"{designator} {record.model}", "designator_model_exact", designator),
                    (f"{record.model}_{designator}", "model_designator_exact", designator),
                    (f"{designator}_{record.model}", "designator_model_exact", designator),
                ]
            )

    if record.part_number:
        for designator in designators:
            terms.extend(
                [
                    (f"{record.part_number} {designator}", "token_set", designator),
                    (f"{designator} {record.part_number}", "token_set", designator),
                ]
            )

    return terms


def _field_matches_folder(field: str, parsed: str, parsed_norm: str, parsed_tokens: frozenset[str]) -> bool:
    """字段与文件夹名是否匹配：整名相等，或任一令牌命中即可。"""
    if not field:
        return False

    field_norm = _normalize_text(field)
    if not field_norm:
        return False

    if field_norm == parsed_norm:
        return True

    if field_norm in parsed_tokens:
        return True

    # 文件夹令牌中只要有一个字段命中也算匹配
    field_tokens = _tokenize(field)
    if field_tokens and field_tokens.issubset(parsed_tokens):
        return True

    return False


def match_folder_in_project(
    folder_name: str,
    project_name: str,
    records: list[ChipRecord],
) -> tuple[ChipRecord, str, str, str] | None:
    """在指定项目上下文中，将文件夹名匹配到 database 记录。

  查找规则：
  - 文件夹名中只要有一个内容与料号、位号或型号匹配即可
  - 支持 ``[名称]_后缀`` 形式，只取 [] 内内容参与匹配
  - 组合名（型号+位号等）仍可匹配，优先级低于单字段命中

  约束：
  - 仅在 database 该项目列有位号的记录中查找
  - 忽略大小写、空格、`_`、`-` 差异
    """
    parsed = parse_chip_folder_name(folder_name)
    if not parsed:
        return None

    parsed_norm = _normalize_text(parsed)
    parsed_tokens = _tokenize(parsed)

    candidates: list[tuple[ChipRecord, str, int, str]] = []

    for record in records:
        designators = record.designators_in(project_name)
        if not designators:
            continue

        matched_for_record = False
        for term, match_type, designator in _build_field_terms(record, project_name):
            if _field_matches_folder(term, parsed, parsed_norm, parsed_tokens):
                priority = _PRIORITY[match_type]
                # 单字段命中时，用 partial_field 区分「整名相等」与「部分令牌命中」
                if match_type in {"designator_exact", "part_number_exact", "model_exact"}:
                    if _normalize_text(term) != parsed_norm and _normalize_text(term) in parsed_tokens:
                        match_type = "partial_field"
                        priority = _PRIORITY["partial_field"]
                candidates.append((record, match_type, priority, designator))
                matched_for_record = True
                break

            if len(parsed_tokens) >= 2 and _tokenize(term) == parsed_tokens:
                candidates.append((record, "token_set", _PRIORITY["token_set"], designator))
                matched_for_record = True
                break

        if matched_for_record:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[2], item[0].row_index))
    best_priority = candidates[0][2]
    best_group = [item for item in candidates if item[2] == best_priority]
    unique_rows = {item[0].row_index for item in best_group}

    if len(unique_rows) == 1:
        record, match_type, _, designator = best_group[0]
        return record, match_type, parsed, designator

    return None


def discover_chip_folders(project_dir: Path) -> list[Path]:
    """发现项目目录下一级的芯片测试文件夹。"""
    if not project_dir.is_dir():
        return []

    folders: list[Path] = []
    for path in sorted(project_dir.iterdir()):
        if path.is_dir() and not path.name.startswith("."):
            folders.append(path)
    return folders


def discover_project_dirs(
    source_paths: list[Path],
    database: Database,
) -> list[tuple[Path, str]]:
    """从源路径中发现与 database 项目列对应的项目文件夹。

  - 若源路径本身名称匹配某项目列 → 视为单个项目目录
  - 若源路径为工作区根目录 → 遍历其子文件夹，名称匹配项目列的纳入
    """
    resolved: list[tuple[Path, str]] = []
    seen: set[str] = set()

    for source in source_paths:
        if not source.is_dir():
            continue

        direct_project = resolve_project_name(source.name, database.project_names)
        if direct_project:
            key = normalize_project_name(direct_project)
            if key not in seen:
                seen.add(key)
                resolved.append((source, direct_project))
            continue

        for child in sorted(source.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            project_name = resolve_project_name(child.name, database.project_names)
            if not project_name:
                continue
            key = normalize_project_name(project_name)
            if key in seen:
                continue
            seen.add(key)
            resolved.append((child, project_name))

    return resolved


def match_project_folders(
    project_dir: Path,
    project_name: str,
    records: list[ChipRecord],
) -> tuple[list[FolderMatch], list[Path]]:
    """匹配单个项目目录中所有可识别的芯片测试文件夹。"""
    matched: list[FolderMatch] = []
    unmatched: list[Path] = []

    for folder in discover_chip_folders(project_dir):
        result = match_folder_in_project(folder.name, project_name, records)
        if result:
            record, match_type, parsed, designator = result
            matched.append(
                FolderMatch(
                    folder_path=folder,
                    project_name=project_name,
                    record=record,
                    match_type=match_type,
                    parsed_folder_name=parsed,
                    matched_designator=designator,
                )
            )
        else:
            unmatched.append(folder)

    return matched, unmatched


def match_all_sources(
    source_paths: list[Path],
    database: Database,
) -> tuple[list[FolderMatch], list[Path], list[str]]:
    """遍历所有源路径中的项目与芯片测试文件夹。"""
    all_matched: list[FolderMatch] = []
    all_unmatched: list[Path] = []
    warnings: list[str] = []

    project_dirs = discover_project_dirs(source_paths, database)
    found_projects = {name for _, name in project_dirs}
    for project in database.project_names:
        if project not in found_projects:
            warnings.append(f"database 中的项目「{project}」未在源路径中找到对应文件夹")

    if not project_dirs:
        warnings.append("未在源路径中发现与 database 项目列匹配的文件夹")

    for project_dir, project_name in project_dirs:
        matched, unmatched = match_project_folders(
            project_dir,
            project_name,
            database.records,
        )
        all_matched.extend(matched)
        all_unmatched.extend(unmatched)

    return all_matched, all_unmatched, warnings
