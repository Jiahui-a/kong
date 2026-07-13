#!/usr/bin/env python3
"""生成 database.xlsx 模板文件。"""

from pathlib import Path

from openpyxl import Workbook


def create_template(output: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "芯片映射"
    sheet.append(["型号", "位号", "料号"])
    sheet.append(["STM32F103C8T6", "U1", "C12345-001"])
    sheet.append(["GD32F303CCT6", "U2", "C12345-002"])
    sheet.append(["W25Q128JVSIQ", "U3", "C12345-003"])
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)
    print(f"已生成模板: {output}")


if __name__ == "__main__":
    create_template(Path(__file__).resolve().parent.parent / "templates" / "database_template.xlsx")
