FROM ubuntu:24.04

ARG COMMANDLINE_TOOLS_VERSION=15859902
ARG COMMANDLINE_TOOLS_SHA256=4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583
ARG ACCEPT_ANDROID_LICENSES=no
ARG ANDROID_API=35

ENV DEBIAN_FRONTEND=noninteractive \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    ANDROID_USER_HOME=/home/android/.android \
    ANDROID_AVD_HOME=/home/android/.android/avd \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    ANDROID_API=${ANDROID_API}
ENV PATH="${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${ANDROID_HOME}/emulator:${PATH}"

RUN test "$ACCEPT_ANDROID_LICENSES" = yes || \
    (echo 'Review https://developer.android.com/studio/terms and build with ACCEPT_ANDROID_LICENSES=yes' >&2; exit 1)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip openjdk-21-jre-headless \
    libasound2t64 libnss3 libnspr4 libdbus-1-3 libpulse0 libglib2.0-0t64 \
    libx11-6 libxcb1 libxcomposite1 libxcursor1 libxi6 libxrender1 libxtst6 \
    libxrandr2 libxkbcommon0 libxkbcommon-x11-0 libglu1-mesa libgl1 libegl1 libvulkan1 \
    && rm -rf /var/lib/apt/lists/*
RUN curl --fail --location --retry 3 \
    "https://dl.google.com/android/repository/commandlinetools-linux-${COMMANDLINE_TOOLS_VERSION}_latest.zip" \
    --output /tmp/tools.zip \
    && echo "${COMMANDLINE_TOOLS_SHA256}  /tmp/tools.zip" | sha256sum --check - \
    && mkdir -p "$ANDROID_HOME/cmdline-tools" \
    && unzip -q /tmp/tools.zip -d "$ANDROID_HOME/cmdline-tools" \
    && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" \
    && rm /tmp/tools.zip
# sdkmanager currently provides these packages; emulator/system image revisions
# float on a rebuild. Save the resulting image by digest for reproducible runs.
RUN yes | sdkmanager --licenses >/dev/null \
    && sdkmanager --channel=0 "platform-tools" "emulator" \
        "system-images;android-${ANDROID_API};google_apis;x86_64" \
    && sdkmanager --list_installed > /opt/android-sdk-packages.txt \
    && useradd --create-home --uid 10001 --shell /bin/bash android

# SDK Manager creates ANDROID_USER_HOME as root during the build, before
# useradd. Give the runtime user ownership so it can create AVDs and ADB keys.
RUN chown -R android:android /home/android

COPY --chmod=755 entrypoint.sh /usr/local/bin/start-emulator
USER android
WORKDIR /home/android
ENTRYPOINT ["/usr/local/bin/start-emulator"]
