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
    """解析项目列中的位号，支持顿号、换行及常见分隔符。

    例如 Excel 单元格内容为 ``U1、U2、U3`` 或::

        U1
        U2

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


def _merge_designator_lists(existing: list[str], new: list[str]) -> list[str]:
    """合并位号列表，保持顺序并去重。"""
    seen = {designator.casefold() for designator in existing}
    merged = list(existing)
    for designator in new:
        key = designator.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(designator)
    return merged


def _merge_into_records(
    records_map: dict[tuple[str, str], ChipRecord],
    part_number: str,
    model: str,
    designators_by_project: dict[str, list[str]],
    row_index: int,
) -> None:
    """将一行项目位号合并到 records_map 中。"""
    key = (part_number, model)
    if key not in records_map:
        records_map[key] = ChipRecord(
            part_number=part_number,
            model=model,
            designators_by_project=designators_by_project,
            row_index=row_index,
        )
        return

    existing = records_map[key]
    merged_projects = dict(existing.designators_by_project)
    for project, designators in designators_by_project.items():
        if project in merged_projects:
            merged_projects[project] = _merge_designator_lists(merged_projects[project], designators)
        else:
            merged_projects[project] = list(designators)

    records_map[key] = ChipRecord(
        part_number=part_number,
        model=model,
        designators_by_project=merged_projects,
        row_index=existing.row_index,
    )


def _build_merged_cell_lookup(sheet) -> dict[tuple[int, int], object]:
    """构建合并单元格查找表，键为 (row, col) 的 0-based 索引。"""
    lookup: dict[tuple[int, int], object] = {}
    merged_cells = getattr(sheet, "merged_cells", None)
    if merged_cells is None:
        return lookup

    for cell_range in merged_cells.ranges:
        top_left_value = sheet.cell(cell_range.min_row, cell_range.min_col).value
        for row in range(cell_range.min_row, cell_range.max_row + 1):
            for col in range(cell_range.min_col, cell_range.max_col + 1):
                lookup[(row - 1, col - 1)] = top_left_value
    return lookup


def _resolve_cell_value(
    value: object,
    row_index: int,
    col_index: int,
    merged_lookup: dict[tuple[int, int], object],
) -> object:
    """读取单元格值，合并单元格非左上角位置回填合并区域的值。"""
    merged_value = merged_lookup.get((row_index, col_index))
    if merged_value is not None:
        return merged_value
    return value


def _read_sheet_rows(sheet) -> list[tuple[object, ...]]:
    """读取工作表全部行，并展开合并单元格的值。"""
    merged_lookup = _build_merged_cell_lookup(sheet)
    rows: list[tuple[object, ...]] = []

    for row_index, row in enumerate(sheet.iter_rows(values_only=True)):
        filled_row: list[object] = []
        for col_index, value in enumerate(row):
            filled_row.append(_resolve_cell_value(value, row_index, col_index, merged_lookup))
        rows.append(tuple(filled_row))

    return rows


def _extract_project_columns(header_row: tuple[object, ...]) -> list[tuple[str, int]]:
    """从表头解析项目列，合并表头单元格产生的重复列名只保留一次。"""
    project_columns: list[tuple[str, int]] = []
    previous_normalized = ""

    for col_index in range(PROJECT_COL_START, len(header_row)):
        project = _cell_text(header_row[col_index])
        if not project:
            continue

        normalized = normalize_project_name(project)
        if normalized == previous_normalized:
            continue

        project_columns.append((project, col_index))
        previous_normalized = normalized

    return project_columns


def load_database(xlsx_path: Path) -> Database:
    """从 Excel 加载芯片映射表。

  列规则（首行为表头）：
  - 第 1 列：可选序号
  - 第 2 列：料号（合并单元格展开后使用合并区内容；未合并且为空则料号为空，不向上继承）
  - 第 3 列：型号（合并单元格展开后使用合并区内容；未合并且为空则型号为空，不向上继承）
  - 第 4 列起：项目名（表头），单元格值为该料号在该项目中的位号

  行规则：
  - 某个项目名下的位号为空时，跳过该项目内容；所有项目列均为空时跳过该行
  - 料号/型号未合并且为空、但项目列有位号时保留该行（料号、型号保持为空）
  - 料号继承仅通过 Excel 合并单元格：展开后合并区内每行都会读到合并区内容
  - 型号同理：仅当当前单元格（含合并单元格）有值时才使用，不查找上一行
  - 同一料号+型号的多行位号会合并到一条记录
  - 同一项目列单元格内多位号可用顿号（、）、换行、逗号、分号等分隔
    """
    if not xlsx_path.is_file():
        raise FileNotFoundError(f"找不到 database 文件: {xlsx_path}")

    workbook = load_workbook(xlsx_path, data_only=True)
    sheet = workbook.active
    rows = _read_sheet_rows(sheet)
    workbook.close()

    if not rows:
        raise ValueError(f"database 文件为空: {xlsx_path}")

    header_row = rows[0]
    if len(header_row) <= MODEL_COL:
        raise ValueError(
            "database.xlsx 列数不足，至少需要：第 2 列料号、第 3 列型号。"
            f"当前表头: {list(header_row)}"
        )

    project_columns = _extract_project_columns(header_row)
    project_names = [project for project, _ in project_columns]

    if not project_names:
        raise ValueError(
            "database.xlsx 未找到项目列（第 4 列起应为项目名表头）。"
            f"当前表头: {list(header_row)}"
        )

    records_map: dict[tuple[str, str], ChipRecord] = {}

    for row_index, row in enumerate(rows[1:], start=2):
        if row is None:
            continue

        # 先展开合并单元格再取值：合并区内每行都会得到合并区内容。
        # 未合并且单元格为空时保持为空，不向上继承上一非空行。
        part_number = _cell_text(row[PART_NUMBER_COL] if PART_NUMBER_COL < len(row) else None)
        model = _cell_text(row[MODEL_COL] if MODEL_COL < len(row) else None)

        designators_by_project: dict[str, list[str]] = {}
        for project, col_index in project_columns:
            designators = parse_designators(row[col_index] if col_index < len(row) else None)
            if designators:
                if project in designators_by_project:
                    designators_by_project[project] = _merge_designator_lists(
                        designators_by_project[project],
                        designators,
                    )
                else:
                    designators_by_project[project] = designators

        # 项目名下位号为空则跳过该项目；整行无任何位号则跳过
        if not designators_by_project:
            continue

        _merge_into_records(
            records_map,
            part_number,
            model,
            designators_by_project,
            row_index,
        )

    if not records_map:
        raise ValueError(f"database.xlsx 中没有有效数据行: {xlsx_path}")

    records = sorted(records_map.values(), key=lambda record: record.row_index)
    return Database(records=records, project_names=project_names)
