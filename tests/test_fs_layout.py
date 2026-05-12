from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fs_layout import UserDataLayout, get_user_data_layout, migrate_legacy_user_data


class TestUserDataLayout(unittest.TestCase):
    def test_paths_and_directory_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            layout = UserDataLayout(base_dir=base_dir)

            self.assertEqual(layout.root, base_dir / "userdata")
            self.assertEqual(layout.user_dcim, base_dir / "userdata" / "User" / "DCIM")
            self.assertEqual(layout.app_data_dir("app.one"), base_dir / "userdata" / "Data" / "Application" / "app.one")

            layout.ensure_directories()

            self.assertTrue(layout.root.exists())
            self.assertTrue(layout.user_dcim.exists())
            self.assertTrue(layout.data_system.exists())
            self.assertTrue(layout.applications.exists())

    def test_get_user_data_layout_uses_workspace_default(self) -> None:
        layout = get_user_data_layout()

        self.assertEqual(layout.base_dir, Path(__file__).resolve().parent.parent)


class TestLegacyMigration(unittest.TestCase):
    def test_migrates_legacy_dcim_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            legacy_dcim = base_dir / "DCIM"
            legacy_dcim.mkdir()
            (legacy_dcim / "photo.jpg").write_text("data", encoding="utf-8")

            result = migrate_legacy_user_data(base_dir=base_dir)

            self.assertEqual(result, {"migrated": 1, "skipped": 0})
            self.assertFalse(legacy_dcim.exists())
            self.assertTrue((base_dir / "userdata" / "User" / "DCIM" / "photo.jpg").exists())

    def test_merges_into_existing_destination_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            legacy_dcim = base_dir / "DCIM"
            legacy_dcim.mkdir()
            (legacy_dcim / "photo.jpg").write_text("data", encoding="utf-8")

            destination = base_dir / "userdata" / "User" / "DCIM"
            destination.mkdir(parents=True)
            (destination / "photo.jpg").write_text("existing", encoding="utf-8")

            result = migrate_legacy_user_data(base_dir=base_dir)

            self.assertEqual(result, {"migrated": 1, "skipped": 0})
            self.assertEqual((destination / "photo.jpg").read_text(encoding="utf-8"), "existing")


if __name__ == "__main__":
    unittest.main()