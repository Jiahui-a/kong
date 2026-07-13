"""单元测试。"""

import shutil
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from cascon_sync.database import load_database
from cascon_sync.matcher import match_folder, match_project_folders
from cascon_sync.sync import sync_projects


def _create_database_xlsx(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["型号", "位号", "料号"])
    sheet.append(["STM32F103C8T6", "U1", "C12345-001"])
    sheet.append(["GD32F303CCT6", "U2", "C12345-002"])
    workbook.save(path)


class CasconSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_load_database(self) -> None:
        xlsx = self.temp_dir / "database.xlsx"
        _create_database_xlsx(xlsx)
        records = load_database(xlsx)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].target_name, "[STM32F103C8T6 C12345-001]")

    def test_match_by_designator(self) -> None:
        xlsx = self.temp_dir / "database.xlsx"
        _create_database_xlsx(xlsx)
        records = load_database(xlsx)
        record = match_folder("U1", records)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.part_number, "C12345-001")

    def test_match_by_part_number(self) -> None:
        xlsx = self.temp_dir / "database.xlsx"
        _create_database_xlsx(xlsx)
        records = load_database(xlsx)
        record = match_folder("C12345-002", records)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.designator, "U2")

    def test_sync_with_internal_rename(self) -> None:
        xlsx = self.temp_dir / "database.xlsx"
        _create_database_xlsx(xlsx)
        records = load_database(xlsx)

        project = self.temp_dir / "project"
        chip_folder = project / "U1"
        chip_folder.mkdir(parents=True)
        (chip_folder / "U1").mkdir()
        (chip_folder / "U1.txt").write_text("data", encoding="utf-8")
        (chip_folder / "readme.txt").write_text("ok", encoding="utf-8")

        output = self.temp_dir / "database"
        report = sync_projects([project], records, output)

        self.assertEqual(report.copied_count, 1)
        dest = output / "[STM32F103C8T6 C12345-001]"
        self.assertTrue(dest.is_dir())
        self.assertTrue((dest / "[STM32F103C8T6 C12345-001]").is_dir())
        self.assertTrue((dest / "[STM32F103C8T6 C12345-001].txt").is_file())
        self.assertTrue((dest / "readme.txt").is_file())

    def test_unmatched_folder_reported(self) -> None:
        xlsx = self.temp_dir / "database.xlsx"
        _create_database_xlsx(xlsx)
        records = load_database(xlsx)

        project = self.temp_dir / "project"
        (project / "UNKNOWN").mkdir(parents=True)

        matched, unmatched = match_project_folders(project, records)
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(unmatched), 1)


if __name__ == "__main__":
    unittest.main()
