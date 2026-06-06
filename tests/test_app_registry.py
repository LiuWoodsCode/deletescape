from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_registry
from app_registry import (
    AppDescriptor,
    _coerce_bool,
    _coerce_int,
    _coerce_str,
    _has_app_class,
    _normalize_app_id,
    _safe_module_name,
    discover_apps,
    load_app_class,
    unload_app_modules,
)


class TestAppRegistryHelpers(unittest.TestCase):
    def test_coercion_helpers(self) -> None:
        self.assertEqual(_coerce_str(123), "123")
        self.assertIsNone(_coerce_str(None))
        self.assertEqual(_coerce_int("7"), 7)
        self.assertIsNone(_coerce_int(True))
        self.assertTrue(_coerce_bool("yes"))
        self.assertFalse(_coerce_bool("off"))

    def test_safe_module_and_app_id(self) -> None:
        self.assertEqual(_safe_module_name("hello-world!"), "deletescape_app_hello_world_")
        self.assertEqual(_normalize_app_id("folder", {"id": " app.one "}), "app.one")
        self.assertEqual(_normalize_app_id("folder", {}), "folder")

    def test_has_app_class_detects_class_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            main_py = Path(temp_dir) / "main.py"
            main_py.write_text("class App:\n    pass\n", encoding="utf-8")
            self.assertTrue(_has_app_class(main_py))

    def test_has_app_class_rejects_missing_or_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            main_py = Path(temp_dir) / "main.py"
            main_py.write_text("def nope():\n    pass\n", encoding="utf-8")
            self.assertFalse(_has_app_class(main_py))
            main_py.write_text("def broken(:\n", encoding="utf-8")
            self.assertFalse(_has_app_class(main_py))


class TestAppRegistryDiscovery(unittest.TestCase):
    def test_discover_apps_registers_manifest_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            apps_root = Path(temp_dir)
            app_dir = apps_root / "sample"
            (app_dir / "Assets").mkdir(parents=True)
            (app_dir / "main.py").write_text("class App:\n    pass\n", encoding="utf-8")
            (app_dir / "icon.png").write_text("icon", encoding="utf-8")
            (app_dir / "manifest.json").write_text(
                """
                {
                  "id": "sample.app",
                  "displayName": "Sample App",
                  "bundleId": "bundle.id",
                  "build": 8,
                  "version": "1.0.0",
                  "permissions": ["camera", null],
                  "icon": "icon.png",
                  "hidden": true,
                  "autostart": true,
                  "launch": {"recieveCustomQSS": true},
                  "file_handlers": [".foo", ".bar"]
                }
                """,
                encoding="utf-8",
            )

            with patch.object(app_registry, "register_handler") as register_handler:
                result = discover_apps(apps_root)

            self.assertIn("sample.app", result)
            descriptor = result["sample.app"]
            self.assertEqual(descriptor.display_name, "Sample App")
            self.assertEqual(descriptor.bundle_id, "bundle.id")
            self.assertEqual(descriptor.build, 8)
            self.assertEqual(descriptor.version, "1.0.0")
            self.assertEqual(descriptor.permissions, ["camera"])
            self.assertTrue(descriptor.hidden)
            self.assertTrue(descriptor.autostart)
            self.assertTrue(descriptor.receive_custom_qss)
            register_handler.assert_called_once_with("sample.app", "Sample App", extensions=[".foo", ".bar"])

    def test_discover_apps_skips_missing_app_class(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            apps_root = Path(temp_dir)
            app_dir = apps_root / "broken"
            (app_dir / "Assets").mkdir(parents=True)
            (app_dir / "main.py").write_text("def not_app():\n    pass\n", encoding="utf-8")
            (app_dir / "manifest.json").write_text("{}", encoding="utf-8")

            with patch.object(app_registry, "register_handler"):
                result = discover_apps(apps_root)

            self.assertEqual(result, {})

    def test_load_and_unload_app_class(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = Path(temp_dir)
            main_py = app_dir / "main.py"
            main_py.write_text("class App:\n    value = 1\n", encoding="utf-8")

            descriptor = AppDescriptor(
                app_id="demo",
                folder=app_dir,
                main_py=main_py,
                display_name="Demo",
                bundle_id=None,
                build=None,
                version=None,
                permissions=[],
                icon_path=None,
                hidden=False,
                autostart=False,
                receive_custom_qss=False,
                module_name="deletescape_app_demo",
                sys_path_entry=str(app_dir),
            )

            app_class = load_app_class(descriptor)
            self.assertIsNotNone(app_class)
            self.assertEqual(app_class.value, 1)
            self.assertIn(descriptor.module_name, sys.modules)

            removed = unload_app_modules(descriptor)
            self.assertGreaterEqual(removed, 1)
            self.assertNotIn(descriptor.module_name, sys.modules)
            self.assertIsNone(descriptor.app_class)


if __name__ == "__main__":
    unittest.main()