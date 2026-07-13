"""将芯片测试文件夹名称与 database 记录匹配。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .database import ChipRecord


@dataclass(frozen=True)
class FolderMatch:
    """文件夹与 database 记录的匹配结果。"""

    folder_path: Path
    record: ChipRecord
    match_type: str


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name).upper()


def _candidate_keys(name: str) -> list[str]:
    """从文件夹名提取可用于匹配的候选关键字。"""
    raw = name.strip()
    if not raw:
        return []

    candidates = [raw]
    normalized = _normalize_name(raw)

    # 去掉常见前后缀
    for pattern in (
        r"^测试[_-]?(?P<core>.+)$",
        r"^(?P<core>.+)[_-]?测试$",
        r"^chip[_-]?(?P<core>.+)$",
        r"^(?P<core>.+)[_-]?chip$",
    ):
        match = re.match(pattern, raw, flags=re.IGNORECASE)
        if match:
            candidates.append(match.group("core"))

    # 按分隔符拆分
    for part in re.split(r"[_\-\s]+", raw):
        part = part.strip()
        if part:
            candidates.append(part)

    # 去重并保持顺序
    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        key = _normalize_name(item)
        if key and key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def _build_lookup(records: list[ChipRecord]) -> dict[str, list[ChipRecord]]:
    lookup: dict[str, list[ChipRecord]] = {}
    for record in records:
        for key in (
            _normalize_name(record.designator),
            _normalize_name(record.part_number),
            _normalize_name(record.model),
            _normalize_name(f"{record.model}{record.part_number}"),
            _normalize_name(f"{record.model}_{record.part_number}"),
            _normalize_name(f"{record.designator}_{record.part_number}"),
        ):
            if key:
                lookup.setdefault(key, []).append(record)
    return lookup


def match_folder(folder_name: str, records: list[ChipRecord]) -> ChipRecord | None:
    """根据文件夹名匹配 database 记录。"""
    lookup = _build_lookup(records)
    keys = _candidate_keys(folder_name)

    # 1. 精确匹配
    for key in keys:
        matched = lookup.get(key)
        if matched:
            if len(matched) == 1:
                return matched[0]
            # 多位号共用同一料号时，优先位号完全一致
            for record in matched:
                if _normalize_name(record.designator) == key:
                    return record
            return matched[0]

    # 2. 包含匹配（文件夹名包含位号或料号）
    folder_norm = _normalize_name(folder_name)
    contain_matches: list[ChipRecord] = []
    for record in records:
        for token in (record.designator, record.part_number):
            token_norm = _normalize_name(token)
            if token_norm and token_norm in folder_norm:
                contain_matches.append(record)

    if len(contain_matches) == 1:
        return contain_matches[0]

    if len(contain_matches) > 1:
        # 优先匹配更长的料号，减少误匹配
        contain_matches.sort(key=lambda r: len(_normalize_name(r.part_number)), reverse=True)
        best = contain_matches[0]
        best_key = _normalize_name(best.part_number)
        if all(_normalize_name(r.part_number) == best_key for r in contain_matches):
            return best

    return None


def discover_chip_folders(
    project_dir: Path,
    *,
    recursive: bool = False,
) -> list[Path]:
    """发现项目目录下的芯片测试文件夹。"""
    if not project_dir.is_dir():
        return []

    folders: list[Path] = []
    if recursive:
        for path in project_dir.rglob("*"):
            if path.is_dir() and not any(part.startswith(".") for part in path.parts):
                folders.append(path)
    else:
        for path in project_dir.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                folders.append(path)

    return sorted(folders)


def match_project_folders(
    project_dir: Path,
    records: list[ChipRecord],
    *,
    recursive: bool = False,
) -> tuple[list[FolderMatch], list[Path]]:
    """匹配项目目录中所有可识别的芯片测试文件夹。"""
    matched: list[FolderMatch] = []
    unmatched: list[Path] = []

    for folder in discover_chip_folders(project_dir, recursive=recursive):
        record = match_folder(folder.name, records)
        if record:
            matched.append(
                FolderMatch(
                    folder_path=folder,
                    record=record,
                    match_type="auto",
                )
            )
        else:
            unmatched.append(folder)

    return matched, unmatched
