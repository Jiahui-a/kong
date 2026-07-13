#!/usr/bin/env python3
"""生成 database.xlsx 模板文件。"""

from pathlib import Path

from openpyxl import Workbook


def create_template(output: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "芯片映射"
    sheet.append(["序号", "料号", "型号", "ProjectA", "ProjectB"])
    sheet.append(["1", "C12345-001", "STM32F103C8T6", "U1", "U5"])
    sheet.append(["2", "C12345-002", "GD32F303CCT6", "U2", ""])
    sheet.append(["3", "C12345-003", "W25Q128JVSIQ", "U3", "U8"])
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)
    print(f"已生成模板: {output}")


if __name__ == "__main__":
    create_template(Path(__file__).resolve().parent.parent / "templates" / "database_template.xlsx")
