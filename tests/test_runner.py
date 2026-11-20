import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("android_runner", Path(__file__).resolve().parents[1] / "android_runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def parse(self, *argv):
        return runner.parser().parse_args(["--session", "chat-one", *argv])

    def test_session_names_and_remote_context_isolation(self):
        for name in ["../other", "Chat One", "-p-other", "", "x" * 41]:
            with self.assertRaises(runner.RunnerError):
                runner.Runner(name)
        one = runner.Runner("chat-one", context="ssh-linux")
        two = runner.Runner("chat-two", context="ssh-linux")
        self.assertEqual(one.docker, ["docker", "--context", "ssh-linux"])
        self.assertEqual(one.compose[-1], "codex-android-chat-one")
        self.assertNotEqual(one.compose, two.compose)

    def test_start_refuses_to_replace_device(self):
        service = runner.Runner("chat-one")
        with patch.object(service, "container", return_value="existing"), patch.object(service, "run") as run:
            with self.assertRaises(runner.RunnerError):
                service.execute(self.parse("start"))
            run.assert_not_called()

    def test_android_shell_text_is_quoted(self):
        service = runner.Runner("chat-one")
        with patch.object(service, "adb") as adb:
            service.execute(self.parse("text", "hello; $(touch /tmp/no)"))
            adb.assert_called_once_with("shell", "input text 'hello;%s$(touch%s/tmp/no)'", capture=False, timeout=120)

    def test_binary_screenshot_roundtrip(self):
        data = b"\x89PNG\r\n\x1a\n\x00\xff\r\n"
        service = runner.Runner("chat-one")
        with tempfile.TemporaryDirectory() as directory, patch.object(service, "adb", return_value=data):
            output = Path(directory) / "nested" / "screen.png"
            service.execute(self.parse("screenshot", "--output", str(output)))
            self.assertEqual(output.read_bytes(), data)
        with patch.object(service, "adb", return_value=b"error: offline"):
            with self.assertRaises(runner.RunnerError):
                service.execute(self.parse("screenshot"))

    def test_install_cleans_upload_after_adb_failure(self):
        service = runner.Runner("chat-one", context="remote")
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "app with spaces.apk"
            apk.write_bytes(b"apk")
            with patch.object(service, "container", return_value="container-id"), \
                    patch.object(service, "run") as run, \
                    patch.object(service, "adb", side_effect=runner.RunnerError("install failed")):
                with self.assertRaisesRegex(runner.RunnerError, "install failed"):
                    service.execute(self.parse("install", str(apk)))
                calls = [call.args[0] for call in run.call_args_list]
                self.assertEqual(calls[0][:5], ["docker", "--context", "remote", "cp", str(apk)])
                self.assertEqual(calls[-1][-3:-1], ["rm", "-f"])

    def test_instrumentation_failure_despite_zero_adb_exit(self):
        service = runner.Runner("chat-one")
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / "instrument.txt")
            args = self.parse("instrument", "example.test/Runner", "--output", output)
            for data in [b"FAILURES!!!\nTests run: 1", b"INSTRUMENTATION_FAILED", b"", b"OK (1 test)\nshortMsg=crash"]:
                with self.subTest(data=data), patch.object(service, "shell", return_value=data):
                    with self.assertRaises(runner.RunnerError):
                        service.execute(args)
                    self.assertEqual(Path(output).read_bytes(), data)
            with patch.object(service, "shell", return_value=b"Time: 1.0\n\nOK (2 tests)\n"):
                service.execute(args)

    def test_timeout_and_nonzero_docker_exit_are_errors(self):
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 10)):
            with self.assertRaisesRegex(runner.RunnerError, "timed out"):
                runner.Runner.run(["docker", "info"], timeout=10)
        failure = subprocess.CompletedProcess(["docker"], 1, b"", b"permission denied")
        with patch.object(subprocess, "run", return_value=failure):
            with self.assertRaisesRegex(runner.RunnerError, "permission denied"):
                runner.Runner.run(["docker", "info"], capture=True)

    def test_adb_targets_only_its_session_and_serial(self):
        service = runner.Runner("chat-one", context="remote")
        with patch.object(service, "container", return_value="only-this-container"), patch.object(service, "run") as run:
            service.execute(self.parse("adb", "--", "shell", "getprop", "ro.build.version.sdk"))
            self.assertEqual(run.call_args.args[0], ["docker", "--context", "remote", "exec",
                             "only-this-container", "adb", "-s", "emulator-5554",
                             "shell", "getprop", "ro.build.version.sdk"])


if __name__ == "__main__":
    unittest.main()
