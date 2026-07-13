"""读取 database.xlsx 中的芯片型号/位号/料号映射。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

# 支持的表头别名（不区分大小写）
MODEL_HEADERS = ("型号", "芯片型号", "model", "part_model")
DESIGNATOR_HEADERS = ("位号", "designator", "ref", "refdes")
PART_NUMBER_HEADERS = ("料号", "part_number", "part no", "partno", "pn")


@dataclass(frozen=True)
class ChipRecord:
    """单条芯片映射记录。"""

    model: str
    designator: str
    part_number: str
    row_index: int

    @property
    def target_name(self) -> str:
        """公盘目标文件夹名：[型号 料号]"""
        return f"[{self.model} {self.part_number}]"


def _normalize_header(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _find_column_index(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    normalized_aliases = {alias.lower() for alias in aliases}
    for index, header in enumerate(headers):
        if header in normalized_aliases:
            return index
    return None


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_database(xlsx_path: Path) -> list[ChipRecord]:
    """从 Excel 文件加载芯片映射表。

    要求首行包含「型号」「位号」「料号」列（支持常见别名）。
    """
    if not xlsx_path.is_file():
        raise FileNotFoundError(f"找不到 database 文件: {xlsx_path}")

    workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()

    if not rows:
        raise ValueError(f"database 文件为空: {xlsx_path}")

    headers = [_normalize_header(cell) for cell in rows[0]]
    model_col = _find_column_index(headers, MODEL_HEADERS)
    designator_col = _find_column_index(headers, DESIGNATOR_HEADERS)
    part_col = _find_column_index(headers, PART_NUMBER_HEADERS)

    missing = []
    if model_col is None:
        missing.append("型号")
    if designator_col is None:
        missing.append("位号")
    if part_col is None:
        missing.append("料号")
    if missing:
        raise ValueError(
            f"database.xlsx 缺少必要列: {', '.join(missing)}。"
            f"当前表头: {list(rows[0])}"
        )

    records: list[ChipRecord] = []
    for row_index, row in enumerate(rows[1:], start=2):
        if row is None:
            continue

        model = _cell_text(row[model_col] if model_col < len(row) else None)
        designator = _cell_text(row[designator_col] if designator_col < len(row) else None)
        part_number = _cell_text(row[part_col] if part_col < len(row) else None)

        if not model and not designator and not part_number:
            continue
        if not model or not part_number:
            raise ValueError(
                f"第 {row_index} 行数据不完整，型号与料号均不能为空: "
                f"型号={model!r}, 位号={designator!r}, 料号={part_number!r}"
            )

        records.append(
            ChipRecord(
                model=model,
                designator=designator,
                part_number=part_number,
                row_index=row_index,
            )
        )

    if not records:
        raise ValueError(f"database.xlsx 中没有有效数据行: {xlsx_path}")

    return records
