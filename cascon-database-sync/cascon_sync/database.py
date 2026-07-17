"""读取 database.xlsx 中的芯片料号/型号及各项目位号映射。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

# 固定列位置（1-based 列号）：第 2 列料号，第 3 列型号
PART_NUMBER_COL = 1  # B 列，0-based index
MODEL_COL = 2  # C 列，0-based index
PROJECT_COL_START = 3  # D 列及之后为各项目位号


@dataclass(frozen=True)
class ChipRecord:
    """单条芯片映射记录。"""

    part_number: str
    model: str
    designators_by_project: dict[str, list[str]]
    row_index: int

    def designators_in(self, project_name: str) -> list[str]:
        """获取该料号在指定项目中的位号列表（支持单元格内换行）。"""
        return list(self.designators_by_project.get(project_name, []))

    def designator_in(self, project_name: str) -> str:
        """获取位号的文本表示（多位号以换行连接）。"""
        return "\n".join(self.designators_in(project_name))

    def target_name(self, project_name: str = "", designator: str = "") -> str:
        """公盘目标文件夹名，仅包含非空的型号、料号、位号。"""
        parts: list[str] = []
        if self.model:
            parts.append(self.model)
        if self.part_number:
            parts.append(self.part_number)
        resolved_designator = designator or (
            self.designators_in(project_name)[0] if project_name and len(self.designators_in(project_name)) == 1 else ""
        )
        if resolved_designator:
            parts.append(resolved_designator)
        if not parts:
            raise ValueError("目标名称至少需要一个非空字段（型号、料号或位号）")
        return f"[{' '.join(parts)}]"


@dataclass
class Database:
    """database.xlsx 解析结果。"""

    records: list[ChipRecord] = field(default_factory=list)
    project_names: list[str] = field(default_factory=list)

    def projects_set(self) -> set[str]:
        return set(self.project_names)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_designators(value: object) -> list[str]:
    """解析项目列中的位号，支持单元格内换行及常见分隔符。

    例如 Excel 单元格内容为::
        U1
        U2
        U3

    将解析为 [\"U1\", \"U2\", \"U3\"]。
    """
    text = _cell_text(value)
    if not text:
        return []

    parts = re.split(r"[\r\n,;，、]+", text)
    designators: list[str] = []
    seen: set[str] = set()
    for part in parts:
        designator = part.strip()
        if not designator:
            continue
        key = designator.casefold()
        if key in seen:
            continue
        seen.add(key)
        designators.append(designator)
    return designators


def normalize_project_name(name: str) -> str:
    """项目名规范化，用于文件夹名与表头匹配。"""
    return re.sub(r"\s+", "", name).casefold()


def resolve_project_name(folder_name: str, known_projects: list[str]) -> str | None:
    """将磁盘上的项目文件夹名解析为 database 表头中的项目名。"""
    folder_key = normalize_project_name(folder_name)
    for project in known_projects:
        if normalize_project_name(project) == folder_key:
            return project
    return None


def load_database(xlsx_path: Path) -> Database:
    """从 Excel 加载芯片映射表。

  列规则（首行为表头）：
  - 第 1 列：可选序号
  - 第 2 列：料号
  - 第 3 列：型号
  - 第 4 列起：项目名（表头），单元格值为该料号在该项目中的位号
    同一单元格内多位号可用换行、逗号、分号等分隔
    """
    if not xlsx_path.is_file():
        raise FileNotFoundError(f"找不到 database 文件: {xlsx_path}")

    workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()

    if not rows:
        raise ValueError(f"database 文件为空: {xlsx_path}")

    header_row = rows[0]
    if len(header_row) <= MODEL_COL:
        raise ValueError(
            "database.xlsx 列数不足，至少需要：第 2 列料号、第 3 列型号。"
            f"当前表头: {list(header_row)}"
        )

    project_names: list[str] = []
    for col_index in range(PROJECT_COL_START, len(header_row)):
        project = _cell_text(header_row[col_index])
        if project:
            project_names.append(project)

    if not project_names:
        raise ValueError(
            "database.xlsx 未找到项目列（第 4 列起应为项目名表头）。"
            f"当前表头: {list(header_row)}"
        )

    records: list[ChipRecord] = []
    for row_index, row in enumerate(rows[1:], start=2):
        if row is None:
            continue

        part_number = _cell_text(row[PART_NUMBER_COL] if PART_NUMBER_COL < len(row) else None)
        model = _cell_text(row[MODEL_COL] if MODEL_COL < len(row) else None)

        if not part_number:
            continue

        designators_by_project: dict[str, list[str]] = {}
        for project, col_index in zip(project_names, range(PROJECT_COL_START, len(header_row))):
            designators = parse_designators(row[col_index] if col_index < len(row) else None)
            if designators:
                designators_by_project[project] = designators

        records.append(
            ChipRecord(
                part_number=part_number,
                model=model,
                designators_by_project=designators_by_project,
                row_index=row_index,
            )
        )

    if not records:
        raise ValueError(f"database.xlsx 中没有有效数据行: {xlsx_path}")

    return Database(records=records, project_names=project_names)
