# Android emulator runner

An **Android 15 / API 35**, Google APIs, x86_64 emulator in Docker. A Python CLI
lets a Codex chat install APKs, inspect and operate the UI, run instrumentation
tests, and download screenshots and logs. No local Android SDK, Python packages,
network API server, or MCP server is required by the client.

## Requirements and platform support

- **Runner:** a Linux x86_64 Docker Engine host with working `/dev/kvm` and
  hardware virtualization enabled. Current Ubuntu LTS releases are suitable.
  A VM needs nested virtualization. Docker Desktop on macOS/Windows is not a
  supported emulator host. Passing `--platform linux/amd64` on an ARM machine
  does not supply KVM or make this emulator accelerated.
- **Client:** Python 3.12+, Docker CLI with Compose v2.20+ on Ubuntu, Windows,
  or macOS. Windows/macOS clients use a remote Linux runner through a Docker
  SSH context. The Python CLI uses argument arrays and writes image bytes
  directly, including on Windows.
- Start with 4 CPU cores, 8 GiB RAM, and 20 GiB free disk on the runner for one
  emulator. Each session is limited to 2 CPUs and 4 GiB RAM; reserve additional
  capacity for concurrent sessions, builds, and Docker images.
- Build app APKs in the app project's existing Gradle environment. This image
  contains emulator tooling, not an app build toolchain. Native libraries in the
  APK must support x86_64; ARM-only APKs are not supported by this runner.

## Configure the Linux host

Install Docker Engine and the Compose plugin using the
[Docker Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/).
Enable virtualization in BIOS/UEFI and, for VMs, on the outer hypervisor. Check
the host:

```sh
ls -l /dev/kvm
stat -c %g /dev/kvm
```

If `/dev/kvm` is absent, fix host virtualization before starting a container.
The user connecting to Docker needs permission to use its daemon. Docker access
provides administrative power on that host; use a dedicated runner you control.
This configuration assumes standard rootful Docker Engine, without user namespace
remapping. Rootless Docker/device mappings need separate host configuration.

On the **client**, copy `.env.example` to `.env` in this directory. Set `KVM_GID`
to the numeric group printed above, from the **Docker host**, not the client.
Review the [Android SDK terms](https://developer.android.com/studio/terms) and set
`ACCEPT_ANDROID_LICENSES=yes` to authorize accepting SDK licenses while building.
Alternatively, pass `build --accept-licenses` to authorize that individual build.
No shell profiles or existing Android installations are modified.

### Local Ubuntu client

From this directory:

```sh
cp .env.example .env
# Edit .env with the host KVM group ID and license decision.
python3 android_runner.py doctor
python3 android_runner.py build
python3 android_runner.py --session chat-one start
```

### Windows/macOS or another remote client

Set up SSH authentication and verify the runner's host key first. The SSH user
must be able to run Docker on the remote host without an interactive sudo prompt.
Create a context once:

```sh
docker context create android-linux --docker host=ssh://runner-user@runner-host
```

Create the local `.env` as above. On Windows use `Copy-Item .env.example .env`.
Then:

```sh
python3 android_runner.py --context android-linux doctor
python3 android_runner.py --context android-linux build
python3 android_runner.py --context android-linux --session chat-one start
```

On Windows replace `python3` with `py -3`. Pass `--context android-linux` on
**every** subsequent command, or set `DOCKER_CONTEXT=android-linux` in the client
environment. APK uploads and artifact downloads use Docker's connection; the app
repository and its paths do not need to exist on the remote runner.

`doctor` checks the Docker connection, host architecture, Compose availability,
and configuration. It cannot prove KVM is usable: `start` checks acceleration in
the container and waits for Android boot completion **and** package-manager
readiness. Allow several minutes on the first boot. If startup fails, the session
is retained for diagnosis:

```sh
python3 android_runner.py --session chat-one status
python3 android_runner.py --session chat-one boot-log
python3 android_runner.py --session chat-one stop
```

The SDK command-line tools archive is pinned and SHA-256 checked. The API is
fixed at 35; stable emulator, platform-tools, and API 35 system-image revisions
are resolved during each build. The image records them in
`/opt/android-sdk-packages.txt`. Builds are therefore not bit-for-bit reproducible.
Keep the resulting image by digest in your private registry if you need identical
tool versions across runners. Review SDK distribution terms before sharing images.
The image currently uses the still available `sdkmanager` and `avdmanager` tools;
Google marks `sdkmanager` deprecated in favor of Android CLI.

## Test an app

Use a unique session name per chat. Commands below assume a local/default Docker
context; add the remote context option when needed.

```sh
python3 android_runner.py --session chat-one install /path/to/app-debug.apk
python3 android_runner.py --session chat-one launch com.example.app
python3 android_runner.py --session chat-one ui --output artifacts/chat-one/ui.xml
python3 android_runner.py --session chat-one screenshot --output artifacts/chat-one/screen.png
```

Inspect the UI XML and compute the center of a target's bounds, then interact:

```sh
python3 android_runner.py --session chat-one tap 540 960
python3 android_runner.py --session chat-one text "hello world"
python3 android_runner.py --session chat-one swipe 540 1500 540 500 --duration 300
python3 android_runner.py --session chat-one key KEYCODE_BACK
python3 android_runner.py --session chat-one logs --output artifacts/chat-one/logcat.txt
```

The coordinates above are examples; derive actual coordinates from the current
UI tree. `text` supports printable ASCII without `%`; use app instrumentation
for Unicode and richer input. Custom-drawn UI elements may not appear in the
accessibility hierarchy and can need app-specific instrumentation.

If launcher resolution fails, specify the activity:

```sh
python3 android_runner.py --session chat-one launch com.example.app --activity com.example.app/.MainActivity
```

Build the app and test APKs in your app project, then run AndroidX instrumentation:

```sh
python3 android_runner.py --session chat-one install /path/to/app-debug-androidTest.apk
python3 android_runner.py --session chat-one instrument com.example.app.test/androidx.test.runner.AndroidJUnitRunner --output artifacts/chat-one/instrumentation.txt
```

The CLI returns nonzero if the runner does not report `OK (N tests)` or reports
a crash/failure. Other instrumentation runners may have different output formats;
use the `adb` escape hatch and inspect their results explicitly.

Additional ADB commands run inside the selected container:

```sh
python3 android_runner.py --session chat-one adb -- shell getprop ro.build.version.sdk
python3 android_runner.py --session chat-one adb -- shell pm clear com.example.app
```

Do not use raw `adb` output redirection for screenshots on Windows; use the
`screenshot` command to preserve bytes. This version deliberately publishes no
ADB ports, so host Gradle `connectedDebugAndroidTest` cannot discover it. Install
the two APKs and use `instrument` as above. An MCP wrapper can call this CLI later
if chats need tool-based access without shell access.

## Isolation and cleanup

Each session maps to a Compose project named `codex-android-<session>` and has
one emulator with its own writable AVD. No host directories, Docker socket,
ports, or persistent data volumes are mounted in the emulator. KVM is the only
device passed through; it does not require `privileged: true`. Android can access
the network through Docker's normal networking. App backend access is something
you must configure for your app's deployment.

`start` refuses to overwrite an existing session. To reset it, explicitly stop
and start it again:

```sh
python3 android_runner.py --session chat-one stop
python3 android_runner.py --session chat-one start
```

`stop` removes the session container and its device data; downloaded artifacts
and the shared Docker image remain. Always collect evidence before cleanup.
Multiple clients using the **same session name and Docker host** share a device;
there is no scheduler, lock manager, automatic expiry, or tenant authentication.
Use unique names and trusted clients. Containers sharing a kernel and KVM are not
a hardened boundary for hostile tenants. No browser viewer is bundled initially;
the CLI provides screenshots for visual inspection.

## Development checks

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile android_runner.py
bash -n entrypoint.sh
docker compose --env-file .env config --quiet
```

Unit tests use mocked Docker calls and temporary files. Actual image builds,
KVM startup, and APK testing need the Linux host described above.

References: [Android emulator acceleration](https://developer.android.com/studio/run/emulator-acceleration),
[emulator command line](https://developer.android.com/studio/run/emulator-commandline),
[ADB](https://developer.android.com/tools/adb),
[SDK Manager](https://developer.android.com/tools/sdkmanager).
