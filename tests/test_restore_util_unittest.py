import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import restore_util


class RestoreUtilTests(unittest.TestCase):
    def test_resolve_silent_python_prefers_project_pythonw(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            scripts_dir = project_root / "venv" / "Scripts"
            scripts_dir.mkdir(parents=True)
            pythonw = scripts_dir / "pythonw.exe"
            pythonw.write_text("", encoding="utf-8")

            with patch.object(sys, "executable", str(project_root / "Python" / "python.exe")):
                command = restore_util.resolve_silent_python(project_root)

            self.assertEqual(command, str(pythonw))

    def test_build_restart_command_uses_main_pyw_for_app_module_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            scripts_dir = project_root / "venv" / "Scripts"
            scripts_dir.mkdir(parents=True)
            pythonw = scripts_dir / "pythonw.exe"
            pythonw.write_text("", encoding="utf-8")

            command = restore_util.build_restart_command("app.main", project_root)

            self.assertEqual(command, [str(pythonw), str(project_root / "main.pyw")])


if __name__ == "__main__":
    unittest.main()
