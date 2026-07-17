"""将芯片测试文件夹名称与 database 记录匹配（按项目上下文）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .database import ChipRecord, Database, normalize_project_name, resolve_project_name

# 匹配优先级（数值越小越优先）
_PRIORITY = {
    "designator_exact": 10,
    "model_designator_exact": 20,
    "designator_model_exact": 20,
    "token_set": 30,
    "model_exact": 40,
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
        """公盘目标文件夹名（按匹配到的位号生成）。"""
        return self.record.target_name(self.project_name, self.matched_designator)


def parse_chip_folder_name(folder_name: str) -> str:
    """解析芯片测试文件夹名，去掉外层 []。"""
    name = folder_name.strip()
    bracket_match = re.fullmatch(r"\[(.*)\]", name, flags=re.DOTALL)
    if bracket_match:
        return bracket_match.group(1).strip()
    return name


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value).upper()


def _tokenize(value: str) -> frozenset[str]:
    parts = re.split(r"[\s_\-]+", value.strip())
    tokens = {_normalize_text(part) for part in parts if part.strip()}
    return frozenset(tokens)


def _build_variants(model: str, designator: str) -> list[tuple[str, str]]:
    """生成可用于比对的命名变体。"""
    variants: list[tuple[str, str]] = []
    if designator:
        variants.append((designator, "designator_exact"))
    if model:
        variants.append((model, "model_exact"))
    if model and designator:
        variants.extend(
            [
                (f"{model} {designator}", "model_designator_exact"),
                (f"{designator} {model}", "designator_model_exact"),
                (f"{model}_{designator}", "model_designator_exact"),
                (f"{designator}_{model}", "designator_model_exact"),
            ]
        )
    return variants


def match_folder_in_project(
    folder_name: str,
    project_name: str,
    records: list[ChipRecord],
) -> tuple[ChipRecord, str, str, str] | None:
    """在指定项目上下文中，将文件夹名匹配到 database 记录。

  查找规则（按优先级）：

  1. **位号精确匹配**：文件夹为 `[U1]` 等形式，内容与该项目列中的位号一致
  2. **型号+位号组合匹配**：文件夹为 `[型号 位号]`、`[位号 型号]` 等混合形式
  3. **令牌集合匹配**：组合名分隔符不同但令牌集合相同（如 `[U1-STM32]`）
  4. **型号精确匹配**：文件夹仅为 `[型号]`，且该料号在本项目有位号

  约束：
  - 仅在 database 该项目列有位号的记录中查找
  - 项目列单元格内换行填写多个位号时，逐一参与匹配
  - 所有比对前会去掉文件夹名外层 `[]` 并忽略大小写、空格、`_`、`-` 差异
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

        for designator in designators:
            for variant, match_type in _build_variants(record.model, designator):
                if _normalize_text(variant) == parsed_norm:
                    candidates.append((record, match_type, _PRIORITY[match_type], designator))
                    break
                elif len(parsed_tokens) >= 2 and _tokenize(variant) == parsed_tokens:
                    candidates.append((record, "token_set", _PRIORITY["token_set"], designator))
                    break
            else:
                continue
            break

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
