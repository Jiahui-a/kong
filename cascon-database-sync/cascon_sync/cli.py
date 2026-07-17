"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .database import load_database
from .sync import sync_projects


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cascon-sync",
        description=(
            "根据 database.xlsx 将各 Cascon 项目中的芯片测试文件夹"
            "复制到公盘 database。重命名仅作用于公盘副本，不修改本地源文件夹。"
        ),
    )
    parser.add_argument(
        "-d",
        "--database",
        required=True,
        type=Path,
        help="database.xlsx 路径（第2列料号、第3列型号、后续列为各项目位号）",
    )
    parser.add_argument(
        "-s",
        "--source",
        nargs="+",
        required=True,
        type=Path,
        help="Cascon 工作区根目录（含各项目子文件夹）或单个项目目录",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="公盘 database 输出目录",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="可选 YAML 配置文件（可覆盖 database/source/output 等参数）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览匹配与重命名结果，不实际复制文件",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="若目标文件夹已存在则覆盖",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        help="将同步结果写入 JSON 报告文件",
    )
    return parser.parse_args(argv)


def _load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("配置文件格式错误，应为 YAML 对象")
    return data


def _apply_config(args: argparse.Namespace) -> argparse.Namespace:
    if not args.config:
        return args

    config = _load_config(args.config)
    if "database" in config and config["database"]:
        args.database = Path(config["database"])
    if "source" in config and config["source"]:
        args.source = [Path(p) for p in config["source"]]
    if "output" in config and config["output"]:
        args.output = Path(config["output"])
    if "dry_run" in config:
        args.dry_run = bool(config["dry_run"])
    if "overwrite" in config:
        args.overwrite = bool(config["overwrite"])
    return args


def _print_report(report) -> None:
    print("=" * 60)
    print("Cascon 芯片测试文件夹同步报告")
    print("=" * 60)

    if report.warnings:
        print("提示:")
        for warning in report.warnings:
            print(f"  * {warning}")
        print("-" * 60)

    for action in report.actions:
        status = "跳过" if action.skipped else "预览" if action.skipped is False and not action.destination.exists() else "完成"
        if action.skipped:
            print(f"[跳过] [{action.project_name}] {action.source.name} -> {action.destination.name}")
            print(f"       原因: {action.skip_reason}")
        else:
            print(f"[{status}] [{action.project_name}] {action.source.name} ({action.match_type})")
            print(f"       -> {action.destination}")
            if action.renamed_internals:
                print("       公盘内部同名项重命名:")
                for old_path, new_path in action.renamed_internals:
                    print(f"         {old_path.name} -> {new_path.name}")

    if report.unmatched_folders:
        print("-" * 60)
        print("未匹配的芯片测试文件夹:")
        for folder in report.unmatched_folders:
            print(f"  - {folder}")

    if report.errors:
        print("-" * 60)
        print("错误:")
        for error in report.errors:
            print(f"  ! {error}")

    print("-" * 60)
    print(
        f"统计: 复制 {report.copied_count} 个, "
        f"跳过 {report.skipped_count} 个, "
        f"未匹配 {len(report.unmatched_folders)} 个, "
        f"错误 {len(report.errors)} 个"
    )


def _write_json_report(report, path: Path) -> None:
    payload = {
        "copied_count": report.copied_count,
        "skipped_count": report.skipped_count,
        "unmatched_count": len(report.unmatched_folders),
        "error_count": len(report.errors),
        "warnings": report.warnings,
        "actions": [
            {
                "source": str(action.source),
                "destination": str(action.destination),
                "project_name": action.project_name,
                "match_type": action.match_type,
                "target_name": action.target_name,
                "model": action.record.model,
                "part_number": action.record.part_number,
                "designator": action.matched_designator or action.record.designator_in(action.project_name),
                "skipped": action.skipped,
                "skip_reason": action.skip_reason,
                "renamed_internals": [
                    {"from": str(old), "to": str(new)}
                    for old, new in action.renamed_internals
                ],
            }
            for action in report.actions
        ],
        "unmatched_folders": [str(folder) for folder in report.unmatched_folders],
        "errors": report.errors,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _apply_config(_parse_args(argv))

    try:
        database = load_database(args.database)
    except (OSError, ValueError) as exc:
        print(f"读取 database 失败: {exc}", file=sys.stderr)
        return 1

    report = sync_projects(
        source_paths=args.source,
        database=database,
        dest_root=args.output,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )

    _print_report(report)

    if args.json_report:
        _write_json_report(report, args.json_report)
        print(f"JSON 报告已写入: {args.json_report}")

    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
