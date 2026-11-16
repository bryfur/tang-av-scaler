# avandroid: the Android toolchain for app/android, built by build.sh on fpga.  (The platform and
# build-tools are the ones AGP 9.5.1 asks for: the SDK here is read-only, nothing is fetched at build time.)
# JDK 21, the Android SDK's command-line tools, platform-tools (adb), one platform and one
# build-tools.  Gradle itself comes from the project's wrapper; its downloads and adb's key
# live in named volumes (androidrun), so they survive the container.
FROM ubuntu:26.04

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      openjdk-21-jdk-headless curl unzip ca-certificates git procps \
    && rm -rf /var/lib/apt/lists/*

ENV ANDROID_HOME=/opt/android-sdk
ARG CMDLINE_TOOLS=16111833
ARG PLATFORM=android-37.0
ARG BUILD_TOOLS=36.0.0
RUN mkdir -p $ANDROID_HOME/cmdline-tools \
    && curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip -o /tmp/ct.zip \
    && unzip -q /tmp/ct.zip -d /tmp/ct && mv /tmp/ct/cmdline-tools $ANDROID_HOME/cmdline-tools/latest \
    && rm -rf /tmp/ct /tmp/ct.zip
ENV PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH
# (the SDK's licences: sdkmanager installs nothing without them)
RUN yes | sdkmanager --licenses >/dev/null \
    && sdkmanager --install "platform-tools" "platforms;${PLATFORM}" "build-tools;${BUILD_TOOLS}" >/dev/null \
    && chmod -R a+rX $ANDROID_HOME

# The caller's user, and the two directories the named volumes mount over (a new volume takes
# the image directory's owner, so they start out the user's)
ARG USER=bryan
ARG UID=1000
ARG GID=1000
RUN (getent group $GID || groupadd -g $GID $USER) \
    && (getent passwd $UID && usermod -l $USER -d /home/$USER -m $(getent passwd $UID | cut -d: -f1) || useradd -m -u $UID -g $GID $USER) \
    && mkdir -p /home/$USER/.gradle /home/$USER/.android && chown -R $UID:$GID /home/$USER
COPY entry.sh /usr/local/bin/entry.sh
ENTRYPOINT ["/usr/local/bin/entry.sh"]
