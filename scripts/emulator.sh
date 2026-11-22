#!/bin/zsh
# Usage: scripts/emulator.sh start|stop   (headless Pixel 6, Android 14, x86_64, hardware-accelerated)
source "$(dirname "$0")/../env.sh"
case "$1" in
  start)
    nohup "$ANDROID_SDK_ROOT/emulator/emulator" -avd dp_test -no-window -no-audio -no-boot-anim -no-snapshot \
      -gpu swiftshader_indirect > /tmp/emulator.log 2>&1 &
    adb wait-for-device
    until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do sleep 3; done
    echo "emulator booted"; adb devices -l ;;
  stop) adb -s emulator-5554 emu kill ;;
  *) echo "usage: $0 start|stop"; exit 2 ;;
esac
