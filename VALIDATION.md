# API 35 runner verification

Verified on November 3, 2026, with Linux x86_64 Docker Engine 29.9.2 and KVM.

- Built `codex-android-emulator:api35` successfully from the Dockerfile.
- Fixed a boot-blocking ownership issue: SDK Manager creates the Android home
  directory as root during image build. The Dockerfile now assigns it to the
  runtime `android` user before starting the emulator.
- The container reported `KVM (version 12) is installed and usable`.
- Android completed its cold boot in 55.4 seconds according to the emulator log.
- Compose health checks passed, including boot completion and package-manager
  readiness. ADB returned `1` for `sys.boot_completed` and `35` for
  `ro.build.version.sdk`.
- The CLI downloaded a valid 1080 × 1920 PNG; visual inspection confirmed the
  Android launcher. UI XML export and logcat download also succeeded.
- All eight CLI unit tests passed. `git diff --check` passed.
- Removed the disposable verification container and network afterward. The
  built image remains available locally.

Installed packages: Android Emulator 37.2.13, platform-tools 37.0.1, and
`system-images;android-35;google_apis;x86_64` revision 9.

Verified local image ID:
`sha256:d29083370d61bc381465b42b45edaab6be8a56cda6818007521a295cb99214dc`.

Local evidence is saved under the git-ignored
`artifacts/verify-api35-1103/`: `boot.png`, `ui.xml`, `boot.log`, and `logcat.txt`.
The git-ignored `.env` records this host's `KVM_GID=991`; build license acceptance
was supplied explicitly with `build --accept-licenses`.

This verifies Linux image building and emulator boot/control. App APK installation,
app instrumentation, concurrent sessions, and Windows/macOS remote clients were
not exercised in this verification run.
