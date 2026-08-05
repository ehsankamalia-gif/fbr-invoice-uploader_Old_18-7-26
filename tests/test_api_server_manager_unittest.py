import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import api_server_manager


class TestApiServerManager(unittest.TestCase):
    def test_resolve_python_command_prefers_pythonw_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            scripts_dir = project_root / "venv" / "Scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)
            (scripts_dir / "python.exe").write_text("", encoding="utf-8")
            (scripts_dir / "pythonw.exe").write_text("", encoding="utf-8")

            with patch.object(api_server_manager, "PROJECT_ROOT", project_root), \
                 patch.object(api_server_manager.sys, "platform", "win32"):
                command = api_server_manager._resolve_python_command()

        self.assertEqual(command, [str(scripts_dir / "pythonw.exe")])

    def test_start_api_server_launches_supervisor_as_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir)
            log_file = runtime_dir / "api_server.log"
            supervisor_script = runtime_dir / "persistent_server.py"
            supervisor_script.write_text("# test supervisor\n", encoding="utf-8")

            process_mock = unittest.mock.Mock()
            process_mock.poll.return_value = None

            with patch.object(api_server_manager, "RUNTIME_DIR", runtime_dir), \
                 patch.object(api_server_manager, "LOG_FILE", log_file), \
                 patch.object(api_server_manager, "STOP_FILE", runtime_dir / "api_server_stop.request"), \
                 patch.object(api_server_manager, "SUPERVISOR_SCRIPT", supervisor_script), \
                 patch.object(api_server_manager, "_ensure_runtime_dir"), \
                 patch.object(api_server_manager, "_resolve_python_command", return_value=["python"]), \
                 patch.object(api_server_manager, "get_api_server_status", side_effect=[
                     {"running": False, "state": "stopped", "message": "API server is not running."},
                     {"running": False, "state": "starting", "message": "Persistent API supervisor started."},
                 ]), \
                 patch("app.services.api_server_manager.subprocess.Popen", return_value=process_mock) as popen_mock, \
                 patch("app.services.api_server_manager.time.sleep"):
                result = api_server_manager.start_api_server()

        self.assertTrue(result["started"])
        self.assertEqual(result["state"], "starting")
        popen_kwargs = popen_mock.call_args.kwargs
        self.assertEqual(
            popen_kwargs["args"] if "args" in popen_kwargs else popen_mock.call_args.args[0],
            [
                "python",
                "-m",
                api_server_manager.SUPERVISOR_MODULE,
                "--host",
                api_server_manager.API_BIND_HOST,
                "--port",
                str(api_server_manager.API_PORT),
            ],
        )
        self.assertEqual(popen_kwargs["cwd"], str(api_server_manager.PROJECT_ROOT))

    def test_stop_api_server_marks_stopped_after_graceful_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stop_file = Path(tmpdir) / "api_server_stop.request"
            initial_status = {
                "running": True,
                "state": "running",
                "message": "API server is running on port 8000.",
                "supervisor_pid": 101,
                "server_pid": 102,
            }
            final_status = {
                "running": False,
                "state": "stopping",
                "message": "Stopping API server...",
                "supervisor_pid": 101,
                "server_pid": 102,
            }

            with patch.object(api_server_manager, "STOP_FILE", stop_file), \
                 patch.object(api_server_manager, "_ensure_runtime_dir"), \
                 patch.object(api_server_manager, "_find_port_pids", return_value={103}), \
                 patch.object(api_server_manager, "_find_api_related_pids", return_value={104}), \
                 patch.object(api_server_manager, "_wait_for_stopped", return_value=True), \
                 patch.object(api_server_manager, "get_api_server_status", side_effect=[initial_status, final_status, {"running": False, "state": "stopped", "message": "API server stopped successfully."}]), \
                 patch.object(api_server_manager, "_write_status_file") as write_status:
                result = api_server_manager.stop_api_server()

        self.assertTrue(result["stopped"])
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(result["message"], "API server stopped successfully.")
        write_status.assert_any_call(
            {
                "state": "stopping",
                "message": "Stopping API server, closing active connections, and cleaning up background processes...",
                "updated_at": unittest.mock.ANY,
                "supervisor_pid": 101,
                "server_pid": 102,
            }
        )
        write_status.assert_any_call(
            {
                "state": "stopped",
                "message": "API server stopped successfully.",
                "updated_at": unittest.mock.ANY,
            }
        )

    def test_stop_api_server_terminates_remaining_related_processes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stop_file = Path(tmpdir) / "api_server_stop.request"
            initial_status = {
                "running": True,
                "state": "running",
                "message": "API server is running on port 8000.",
                "supervisor_pid": 11,
                "server_pid": 12,
            }
            final_status = {
                "running": False,
                "state": "stopped",
                "message": "API server stopped successfully.",
            }

            with patch.object(api_server_manager, "STOP_FILE", stop_file), \
                 patch.object(api_server_manager, "_ensure_runtime_dir"), \
                 patch.object(api_server_manager, "_find_port_pids", return_value={13}), \
                 patch.object(api_server_manager, "_find_api_related_pids", return_value={14}), \
                 patch.object(api_server_manager, "_wait_for_stopped", return_value=False), \
                 patch.object(api_server_manager, "_is_port_open", return_value=False), \
                 patch.object(api_server_manager, "get_api_server_status", side_effect=[initial_status, final_status]), \
                 patch.object(api_server_manager, "_write_status_file"), \
                 patch.object(api_server_manager, "_terminate_pid") as terminate_pid:
                result = api_server_manager.stop_api_server()

        self.assertTrue(result["stopped"])
        self.assertEqual(
            [call.args[0] for call in terminate_pid.call_args_list],
            [14, 13, 12, 11],
        )


if __name__ == "__main__":
    unittest.main()
