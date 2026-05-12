from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import file_handlers
from file_handlers import get_handlers_for_path, open_with_app, register_handler, unregister_handler


class TestFileHandlers(unittest.TestCase):
    def tearDown(self) -> None:
        file_handlers._HANDLERS.clear()

    def test_register_unregister_and_lookup(self) -> None:
        register_handler("app.one", "App One", extensions=[".TXT", ".md"])
        register_handler("app.two", "App Two", extensions=[".png"])

        matches = get_handlers_for_path(Path("note.txt"))
        self.assertEqual([match["app_id"] for match in matches], ["app.one"])

        unregister_handler("app.one")
        self.assertEqual(get_handlers_for_path(Path("note.txt")), [])

    def test_lookup_ignores_missing_extensions(self) -> None:
        register_handler("app.one", "App One", extensions=[])
        self.assertEqual(get_handlers_for_path(Path("note.txt")), [])

    def test_open_with_app_writes_intent_and_launches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            with unittest.mock.patch.object(file_handlers, "__file__", str(base_dir / "file_handlers.py")):
                launched: list[str] = []

                class Window:
                    def launch_app(self, app_id: str) -> None:
                        launched.append(app_id)

                open_with_app(Window(), "demo", Path("/tmp/example.txt"))

            intent_path = base_dir / "userdata" / "Data" / "Application" / "demo" / "open_intent.json"
            self.assertTrue(intent_path.exists())
            self.assertEqual(launched, ["demo"])


if __name__ == "__main__":
    unittest.main()