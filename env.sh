# Source this file: `source env.sh`
# adb and scrcpy are installed per user (no sudo) in ~/.local/opt. Change the paths if yours differ.
export ANDROID_PT="$HOME/.local/opt/platform-tools"
export SCRCPY_DIR="$HOME/.local/opt/scrcpy-macos-x86_64-v5.0.1"
export ADB="$ANDROID_PT/adb"            # scrcpy honours $ADB, so both use one adb server
export SCRCPY_SERVER_PATH="$SCRCPY_DIR/scrcpy-server"
export PATH="$ANDROID_PT:$SCRCPY_DIR:$PATH"

# Optional: local emulator for testing without the phone (see scripts/emulator.sh)
export JAVA_HOME="$HOME/.local/opt/jdk/Contents/Home"
export ANDROID_SDK_ROOT="$HOME/.local/opt/android-sdk"
export ANDROID_AVD_HOME="$HOME/.local/opt/avd"
