#!/bin/bash
set -euo pipefail

if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
    echo 'KVM unavailable: use a Linux x86_64 Docker host and set KVM_GID to the host /dev/kvm group ID.' >&2
    exit 1
fi
emulator -accel-check
mkdir -p "$ANDROID_AVD_HOME"
printf 'no\n' | avdmanager create avd --force --name codex \
    --package "system-images;android-${ANDROID_API};google_apis;x86_64"
cat >> "$ANDROID_AVD_HOME/codex.avd/config.ini" <<'EOF'
hw.lcd.width=1080
hw.lcd.height=1920
hw.lcd.density=420
hw.keyboard=yes
disk.dataPartition.size=4G
EOF

# ADB remains inside the container. docker exec targets emulator-5554 explicitly.
adb start-server
exec emulator -avd codex -port 5554 -accel on \
    -no-window -no-audio -no-boot-anim -no-snapshot \
    -gpu software -memory 2048 -cores 2 -no-metrics
