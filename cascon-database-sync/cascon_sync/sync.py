"""复制并重命名芯片测试文件夹到公盘 database。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .database import ChipRecord
from .matcher import FolderMatch, match_project_folders


@dataclass
class SyncAction:
    """单次同步操作记录。"""

    source: Path
    destination: Path
    record: ChipRecord
    renamed_internals: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class SyncReport:
    """同步结果汇总。"""

    actions: list[SyncAction] = field(default_factory=list)
    unmatched_folders: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def copied_count(self) -> int:
        return sum(1 for action in self.actions if not action.skipped)

    @property
    def skipped_count(self) -> int:
        return sum(1 for action in self.actions if action.skipped)


def _rename_same_name_children(dest_folder: Path, original_name: str, new_name: str) -> list[tuple[Path, Path]]:
    """将目标文件夹内与原始文件夹同名的文件/子文件夹重命名。"""
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
    new_name = folder_match.record.target_name
    dest = dest_root / new_name

    action = SyncAction(source=src, destination=dest, record=folder_match.record)

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
    project_dirs: list[Path],
    database_records: list[ChipRecord],
    dest_root: Path,
    *,
    recursive: bool = False,
    dry_run: bool = False,
    overwrite: bool = False,
) -> SyncReport:
    """同步多个项目目录中的芯片测试文件夹。"""
    report = SyncReport()
    dest_root.mkdir(parents=True, exist_ok=True)

    seen_targets: dict[str, Path] = {}

    for project_dir in project_dirs:
        if not project_dir.is_dir():
            report.errors.append(f"项目目录不存在: {project_dir}")
            continue

        matched, unmatched = match_project_folders(
            project_dir,
            database_records,
            recursive=recursive,
        )
        report.unmatched_folders.extend(unmatched)

        for folder_match in matched:
            target_key = folder_match.record.target_name
            if target_key in seen_targets:
                report.errors.append(
                    f"重复目标名称 {target_key}: "
                    f"{seen_targets[target_key]} 与 {folder_match.folder_path}"
                )
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
            except Exception as exc:  # noqa: BLE001 - 汇总错误继续处理
                report.errors.append(
                    f"同步失败 {folder_match.folder_path}: {exc}"
                )

    return report
