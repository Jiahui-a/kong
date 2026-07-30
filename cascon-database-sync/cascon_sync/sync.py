"""复制并重命名芯片测试文件夹到公盘 database。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .database import Database
from .matcher import FolderMatch, match_all_sources


@dataclass
class SyncAction:
    """单次同步操作记录。"""

    source: Path
    destination: Path
    project_name: str
    record: object
    match_type: str = ""
    matched_designator: str = ""
    renamed_internals: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def target_name(self) -> str:
        return self.record.target_name(self.project_name, self.matched_designator)  # type: ignore[union-attr]


@dataclass
class SyncReport:
    """同步结果汇总。"""

    actions: list[SyncAction] = field(default_factory=list)
    unmatched_folders: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def copied_count(self) -> int:
        return sum(1 for action in self.actions if not action.skipped)

    @property
    def skipped_count(self) -> int:
        return sum(1 for action in self.actions if action.skipped)


def _rename_same_name_children(dest_folder: Path, original_name: str, new_name: str) -> list[tuple[Path, Path]]:
    """将公盘副本内与原始文件夹同名的文件/子文件夹重命名。"""
    renamed: list[tuple[Path, Path]] = []

    for child in dest_folder.iterdir():
        if child.name == original_name:
            target = dest_folder / new_name
        elif child.is_file() and child.stem == original_name:
            target = dest_folder / f"{new_name}{child.suffix}"
        else:
            continue

        if target.exists():
            raise FileExistsError(f"重命名冲突: {child} -> {target}")

        child.rename(target)
        renamed.append((child, target))

    return renamed


def _copy_folder(src: Path, dest: Path) -> None:
    if dest.exists():
        raise FileExistsError(f"目标已存在: {dest}")
    shutil.copytree(src, dest)


def sync_folder(
    folder_match: FolderMatch,
    dest_root: Path,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> SyncAction:
    """复制单个芯片测试文件夹到公盘并重命名。

    仅修改公盘目标目录（dest），不会改动本地源文件夹（src）。
    """
    src = folder_match.folder_path
    original_name = src.name
    new_name = folder_match.target_name
    dest = dest_root / new_name

    action = SyncAction(
        source=src,
        destination=dest,
        project_name=folder_match.project_name,
        record=folder_match.record,
        match_type=folder_match.match_type,
        matched_designator=folder_match.matched_designator,
    )

    if dest.exists():
        if overwrite:
            if not dry_run:
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
        else:
            action.skipped = True
            action.skip_reason = f"目标已存在: {dest}"
            return action

    if dry_run:
        action.renamed_internals = [
            (src / original_name, dest / new_name),
        ]
        return action

    _copy_folder(src, dest)
    action.renamed_internals = _rename_same_name_children(dest, original_name, new_name)
    return action


def sync_projects(
    source_paths: list[Path],
    database: Database,
    dest_root: Path,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> SyncReport:
    """同步源路径中各项目的芯片测试文件夹到公盘。"""
    report = SyncReport()
    dest_root.mkdir(parents=True, exist_ok=True)

    matched, unmatched, warnings = match_all_sources(source_paths, database)
    report.unmatched_folders = unmatched
    report.warnings = warnings

    seen_targets: dict[str, Path] = {}

    for folder_match in matched:
        try:
            target_key = folder_match.target_name
        except ValueError as exc:
            report.errors.append(f"同步失败 {folder_match.folder_path}: {exc}")
            continue

        if target_key in seen_targets:
            # 公盘命名为 [料号_型号] 后，多项目/多位号可能指向同一目标；保留首次，其余跳过。
            previous = seen_targets[target_key]
            action = SyncAction(
                source=folder_match.folder_path,
                destination=dest_root / target_key,
                project_name=folder_match.project_name,
                record=folder_match.record,
                match_type=folder_match.match_type,
                matched_designator=folder_match.matched_designator,
                skipped=True,
                skip_reason=(
                    f"目标 {target_key} 已由 {previous} 同步，"
                    f"跳过重复源 {folder_match.folder_path}"
                ),
            )
            report.actions.append(action)
            report.warnings.append(action.skip_reason)
            continue

        try:
            action = sync_folder(
                folder_match,
                dest_root,
                dry_run=dry_run,
                overwrite=overwrite,
            )
            report.actions.append(action)
            if not action.skipped:
                seen_targets[target_key] = folder_match.folder_path
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"同步失败 {folder_match.folder_path}: {exc}")

    return report
