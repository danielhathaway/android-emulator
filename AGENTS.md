# Using the API 35 emulator from a chat

- All software in this project should be compatible with the latest versions
  of Ubuntu LTS, Windows, and macOS. The client supports all three; the Docker
  emulator host requires Linux x86_64 with KVM as documented in README.md.
- Follow README.md setup, then use `android_runner.py` for Docker sessions.
  The runner is Linux x86_64 with KVM; clients can be Ubuntu, Windows, or macOS.
- Choose a unique `--session` per chat and retain the same Docker `--context`.
  Never reuse or stop another chat's session. Build once per Docker host.
- `start` waits for Android readiness. Use `boot-log` if it fails.
- Build APKs with the app's existing Gradle wrapper, then use `install` and `launch`.
- Dump `ui` before interacting. Compute tap coordinates from current XML bounds;
  use `screenshot` to verify the visible outcome. Re-dump after navigation.
- Put artifacts in `artifacts/<session>/` and use explicit `--output` paths.
  Open downloaded screenshots to inspect them; successful input alone is not QA.
- For instrumentation, install app and test APKs and use `instrument`.
- Capture logs and relevant screenshots before `stop`, which deletes device data.
- This is a CLI integration, not an MCP server. No ADB port is published.
