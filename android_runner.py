#!/usr/bin/env python3
"""Portable Docker/ADB client. Python 3.12+, no third-party dependencies."""

import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parent
SERIAL = "emulator-5554"


class RunnerError(Exception):
    pass


class Runner:
    def __init__(self, session, context=None, env_file=None):
        if session is not None and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", session):
            raise RunnerError("Session must be 1–40 lowercase letters, digits, or hyphens, starting with a letter or digit.")
        self.session = session
        self.docker = ["docker"] + (["--context", context] if context else [])
        self.compose = self.docker + ["compose", "--project-directory", str(ROOT)]
        env_path = Path(env_file).resolve() if env_file else ROOT / ".env"
        if env_file or env_path.exists():
            self.compose += ["--env-file", str(env_path)]
        self.compose += ["-f", str(ROOT / "compose.yaml"), "-p", f"codex-android-{session or 'build'}"]

    @staticmethod
    def run(argv, *, capture=False, timeout=120, env=None):
        try:
            result = subprocess.run(argv, capture_output=capture, timeout=timeout, env=env, check=False)
        except FileNotFoundError as exc:
            raise RunnerError(f"Executable not found: {argv[0]}. Install Docker CLI with Compose v2.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RunnerError(f"Command timed out after {timeout}s: {shlex.join(argv)}") from exc
        if result.returncode:
            detail = result.stderr.decode(errors="replace").strip() if capture else "See command output above."
            raise RunnerError(f"Command failed ({result.returncode}): {shlex.join(argv)}\n{detail}")
        return result.stdout if capture else b""

    def container(self, required=True):
        ids = self.run(self.compose + ["ps", "--all", "--quiet", "emulator"], capture=True).decode().split()
        if len(ids) > 1:
            raise RunnerError("Expected one emulator per session.")
        if not ids and required:
            raise RunnerError(f"Session {self.session!r} does not exist. Run start first.")
        return ids[0] if ids else None

    def adb(self, *args, capture=False, timeout=120):
        return self.run(self.docker + ["exec", self.container(), "adb", "-s", SERIAL, *args],
                        capture=capture, timeout=timeout)

    def shell(self, *args, capture=False, timeout=120):
        # adb shell joins its arguments into remote shell text. Quote each token
        # for Android's shell, independently of the local OS.
        return self.adb("shell", shlex.join(args), capture=capture, timeout=timeout)

    def save(self, path, data):
        output = Path(path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        print(output)

    def execute(self, args):
        command = args.command
        if command == "doctor":
            self.run(self.docker + ["version"], timeout=30)
            self.run(self.docker + ["compose", "version"], timeout=30)
            host = self.run(self.docker + ["info", "--format", "{{.OSType}}/{{.Architecture}}"], capture=True).decode().strip()
            if host not in {"linux/x86_64", "linux/amd64"}:
                raise RunnerError(f"Requires a Linux x86_64 Docker host; selected host reports {host}.")
            self.run(self.compose + ["config", "--quiet"])
            print("Docker host and configuration checked. start also checks KVM access and Android readiness.")
        elif command == "build":
            env = os.environ.copy()
            if args.accept_licenses:
                env["ACCEPT_ANDROID_LICENSES"] = "yes"
            self.run(self.compose + ["build", "emulator"], timeout=args.timeout, env=env)
        elif command == "start":
            if self.container(required=False):
                raise RunnerError("Session already exists. Use status, or stop it before creating a fresh session.")
            self.run(self.compose + ["up", "--detach", "--no-build", "--wait", "--wait-timeout", str(args.timeout), "emulator"],
                     timeout=args.timeout + 60)
            print(f"Session {self.session} is ready (API 35).")
        elif command == "stop":
            self.run(self.compose + ["down", "--volumes", "--remove-orphans"], timeout=120)
        elif command == "status":
            self.run(self.compose + ["ps", "--all"])
        elif command == "boot-log":
            self.run(self.compose + ["logs", "--no-color", "--tail", "200", "emulator"])
        elif command == "install":
            apk = Path(args.apk).resolve()
            if not apk.is_file() or apk.suffix.lower() != ".apk":
                raise RunnerError(f"Expected an existing APK file: {apk}")
            container = self.container()
            remote = f"/tmp/{uuid.uuid4().hex}.apk"
            self.run(self.docker + ["cp", str(apk), f"{container}:{remote}"])
            try:
                # docker cp creates root-owned files; allow the non-root ADB user
                # to read uploads even when the local APK has restrictive modes.
                self.run(self.docker + ["exec", "--user", "0", container, "chmod", "644", remote])
                self.adb("install", "-r", remote, timeout=300)
            finally:
                self.run(self.docker + ["exec", "--user", "0", container, "rm", "-f", remote])
        elif command == "launch":
            if args.activity:
                self.shell("am", "start", "-W", "-n", args.activity)
            else:
                activity = self.shell("cmd", "package", "resolve-activity", "--brief", "-a",
                                      "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
                                      args.package, capture=True).decode().strip().splitlines()
                if not activity or "/" not in activity[-1]:
                    raise RunnerError(f"No launcher activity found for {args.package}; pass --activity package/activity.")
                self.shell("am", "start", "-W", "-n", activity[-1])
        elif command == "screenshot":
            data = self.adb("exec-out", "screencap", "-p", capture=True)
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RunnerError("Emulator did not return a PNG screenshot.")
            self.save(args.output, data)
        elif command == "ui":
            self.shell("uiautomator", "dump", "/data/local/tmp/codex-window.xml", capture=True)
            data = self.adb("exec-out", "cat", "/data/local/tmp/codex-window.xml", capture=True)
            self.save(args.output, data)
        elif command == "logs":
            self.save(args.output, self.adb("logcat", "-d", "-v", "threadtime", capture=True))
        elif command == "tap":
            self.shell("input", "tap", str(args.x), str(args.y))
        elif command == "swipe":
            self.shell("input", "swipe", *map(str, [args.x1, args.y1, args.x2, args.y2, args.duration]))
        elif command == "text":
            if not args.value.isascii() or "%" in args.value or any(ord(c) < 32 for c in args.value):
                raise RunnerError("input text supports printable ASCII without %. Use an instrumentation test for other text.")
            self.shell("input", "text", args.value.replace(" ", "%s"))
        elif command == "key":
            self.shell("input", "keyevent", args.code)
        elif command == "instrument":
            result = self.shell("am", "instrument", "-w", "-r", args.component,
                                capture=True, timeout=args.timeout)
            self.save(args.output, result)
            text = result.decode(errors="replace")
            if not re.search(r"(?m)^OK \(\d+ tests?\)", text) or any(marker in text for marker in
                    ["FAILURES!!!", "INSTRUMENTATION_FAILED", "shortMsg=", "Process crashed"]):
                raise RunnerError("Instrumentation did not report a successful test run; inspect the saved output.")
        elif command == "adb":
            tail = args.arguments
            if tail[:1] == ["--"]:
                tail = tail[1:]
            if not tail:
                raise RunnerError("Provide an adb command after --.")
            self.adb(*tail, timeout=args.timeout)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--session", help="Unique chat/session name; required except for build and doctor")
    p.add_argument("--context", help="Docker context, including SSH contexts for remote Linux hosts")
    p.add_argument("--env-file", help="Compose environment file (default: .env beside this script)")
    sub = p.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Build API 35 image on the selected Docker host")
    build.add_argument("--accept-licenses", action="store_true", help="Accept Android SDK licenses during image build")
    build.add_argument("--timeout", type=int, default=3600)
    sub.add_parser("doctor")
    start = sub.add_parser("start", help="Create a fresh session; refuses to replace an existing one")
    start.add_argument("--timeout", type=int, default=360)
    for name in ["stop", "status", "boot-log"]:
        sub.add_parser(name)
    sub.add_parser("install").add_argument("apk")
    launch = sub.add_parser("launch")
    launch.add_argument("package")
    launch.add_argument("--activity", help="Explicit package/activity component")
    for name, default in [("screenshot", "screen.png"), ("ui", "ui.xml"), ("logs", "logcat.txt")]:
        sub.add_parser(name).add_argument("--output", default=f"artifacts/{default}")
    tap = sub.add_parser("tap")
    for coord in ["x", "y"]:
        tap.add_argument(coord, type=int)
    swipe = sub.add_parser("swipe")
    for coord in ["x1", "y1", "x2", "y2"]:
        swipe.add_argument(coord, type=int)
    swipe.add_argument("--duration", type=int, default=300)
    sub.add_parser("text").add_argument("value")
    sub.add_parser("key").add_argument("code", help="Android key code, e.g. KEYCODE_BACK")
    instrument = sub.add_parser("instrument")
    instrument.add_argument("component", help="test.package/androidx.test.runner.AndroidJUnitRunner")
    instrument.add_argument("--output", default="artifacts/instrumentation.txt")
    instrument.add_argument("--timeout", type=int, default=900)
    adb = sub.add_parser("adb", help="Pass through adb arguments; no local adb installation needed")
    adb.add_argument("--timeout", type=int, default=120)
    adb.add_argument("arguments", nargs=argparse.REMAINDER)
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.command not in {"build", "doctor"} and not args.session:
        p.error("--session is required for this command")
    try:
        Runner(args.session, args.context, args.env_file).execute(args)
    except (RunnerError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. The session may still be running; use status or stop.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
