# Research findings: full-touch Android agent

Status legend: `verified` = read from a primary source in this session. `unverified` = from memory, to be checked.

## Environment (verified)

- Mac: macOS 15.7.5, Intel x86_64.
- Phone: realme 9 (USB vendor 0x22d9, product 0x276a). Visible to macOS over USB.
- `adb devices` is empty. The phone is in USB tethering mode, which does not expose an ADB interface. USB debugging must be enabled.
- Homebrew install failed (`/usr/local/share/man/man8` not writable). Installed instead to `~/.local/opt`: platform-tools 37.0.3 and scrcpy 5.0.1 (x86_64 build). See `env.sh`.

## F1. scrcpy gives real multi-touch injection (verified)

Sources: scrcpy `doc/develop.md`; `ControlMessage.java`; `ControlMessageReader.java` (master branch).

- The server is a Java app run as the `shell` user via `app_process`. It injects events with the hidden `InputManager.injectInputEvent()`. That is the same level as `adb shell input`, but with a persistent socket instead of a process spawn per event.
- Touch message fields: `action` (MotionEvent action), `pointerId` (long), `position` (x, y, screenWidth, screenHeight), `pressure`, `actionButton`, `buttons`. A distinct `pointerId` per finger means multi-touch (pinch, rotate, multi-finger swipe) is expressible.
- Other message types in the protocol: key events, text injection (max 300 chars), scroll (h/v, range -16..16), back-or-screen-on, notification/settings panel expand, clipboard get/set (with paste), rotate device, UHID create/input/destroy (virtual keyboard/mouse/gamepad), `START_APP` (by package name), reset video, resize display, scan file.
- Video: H.264 (also H.265, AV1, VP8, VP9) over a socket, with a 12-byte frame header. Frames are only sent when the screen changes.
- The protocol is internal and unversioned. Client and server versions must match exactly (`app_process / com.genymobile.scrcpy.Server 5.0.1 ...`). Pin the server jar to the version we implement against.
- The server can run standalone with `raw_stream=true` and be driven by any client.

Implication: write our own thin client in Python for the control socket and video socket. Do not shell out to `adb input`.

## F2. Existing agent frameworks (partly verified)

- AndroidWorld (Google Research): 116 tasks, 20 apps, runs on an emulator with a gRPC accessibility forwarding app. Verified from README. It needs an emulator (Pixel 6, API 33), so it is not directly runnable on the realme 9. We would need a real-device adapter or an emulator for benchmarking.
- Mobile-Agent-v3 / GUI-Owl (arXiv 2508.15144, verified from abstract): GUI-Owl-7B reaches 66.4 on AndroidWorld. Mobile-Agent-v3 reaches 73.3 (open-source SOTA as claimed by the authors).
- mobile-mcp (mobile-next, verified from README): MCP server with "accessibility-first" snapshots and coordinate taps from screenshots, for Android and iOS.
- Mobilerun/DroidRun (verified from README): combines accessibility tree with screenshots, uses a companion "Portal" app on Android, CLI/Python API. Claims 91.4% on its own benchmark (not independently checked).
- Not yet read: AppAgent, DroidBot-GPT, AutoDroid, Open-AutoGLM, UI-TARS, OS-Atlas, SeeClick, Aguvis, Ferret-UI, AndroidLab, AndroidControl, AITW. Next research cycles.

## Open questions

1. Does the realme 9 (realme UI) allow input injection over ADB without extra toggles? Many OEM skins gate it behind "USB debugging (Security settings)" or a similar switch. Test: send `input tap` and a scrcpy touch event.
2. Do scrcpy touch events carry enough fidelity (pointer count, timing) to scroll fling lists and pinch-zoom maps the same as a finger? Test on-device.
3. How much of a typical app's UI is invisible to the accessibility tree (WebView, Flutter, games)? Measure on the apps the user cares about.
4. What are the latency and token costs per step for tree-only vs. screenshot-only vs. hybrid?

## Hypotheses

- H1: A hybrid observation (accessibility tree plus screenshot) with action verification beats screenshot-only agents on reliability at lower cost per step.
- H2: Caching successful trajectories as replayable skills cuts cost and latency for repeated tasks by a large factor, with the LLM only invoked on divergence.
- H3: Pixel-diff plus accessibility-event "settle detection" removes a class of failures caused by acting on a mid-transition screen.

## Build status (end of session 2)

- Built `droidpilot`: MCP server (mcp 1.30, FastMCP, stdio) with 18 tools, own scrcpy control client, perception, action verification.
- Verified without a phone: wire-format encoders, UI parsing, coordinate mapping, change detection, MCP handshake and graceful error (7 pytest tests pass).
- Verified: Gemini CLI reports the server `Connected`; `kiro-cli mcp status` reports configured.
- Not verified: any real tool call from Claude Code, Codex, Gemini, or Kiro-headless. Claude is not logged in, Codex returns 401, Gemini's free-tier client is rejected (`UNSUPPORTED_CLIENT`), Kiro headless did not surface MCP tools.
- Not verified: everything that touches the phone. adb still lists no device (USB product 0x276a, tethering mode, no ADB interface).
- Unverified assumptions in code, to test first on-device: scrcpy 5.0.1 accepts `send_device_meta=false` plus a dummy byte on a control-only forward tunnel; pointer IDs 0,1 map to independent fingers; `uiautomator dump /dev/tty` works on realme UI.

## Build status (end of session 3): validated on an emulator

Phone still not visible to adb (tethering mode). To test anyway, installed user-local JDK 17, Android cmdline-tools, emulator 37.3.10 and a Pixel 6 / Android 14 x86_64 AVD (`dp_test`). `scripts/emulator.sh start|stop`.

Verified on the emulator:
- scrcpy 5.0.1 handshake works as written (control-only forward tunnel, dummy byte, `send_device_meta=false`).
- `droidpilot doctor` passes; `tests/e2e_device.py` passes 12/12 through the real MCP stdio server (open app, observe, scroll both ways, long-press, pinch, 3-finger gesture, keys, bad index error).
- Multi-touch is real: `dumpsys input` during a 3-finger hold shows `pointerIds=...0111` on a TOUCHSCREEN source.
- uiautomator dump returns `null root node` on the first call after boot; a retry fixes it (added).

Bug found and fixed by the e2e run: adb subprocesses inherited the MCP server's stdin and swallowed JSON-RPC messages, hanging every call after the first. All subprocesses now use `stdin=DEVNULL`.

Still unverified: anything on the realme 9 (OEM injection gate, realme UI dump), and real prompts through Claude/Codex/Gemini/Kiro (auth).
Latency on the emulator is about 6 s per verified action (1.5 s per screencap, 3+ per action); real-phone figure unknown.

## Build status (session 4): validated on the realme 9

- Phone: RMX3521 (realme 9), Android 14 / SDK 34, 1080x2400, serial <serial>. USB debugging enabled; adb sees it as `device`.
- `droidpilot doctor` passes. scrcpy 5.0.1 control backend starts on the phone, no extra OEM gate hit.
- `tests/e2e_device.py`: 12/12 pass on the phone (Settings scroll both ways changed the screen, so injected touch is accepted).
- Multi-touch confirmed: `dumpsys input` during a 3-finger hold shows `pointerIds=...0111`.
- Latency on the phone: screencap (PNG) 1.25 s, uiautomator dump 2.6 s, one verified tap 6.1 s. Too slow. Next: raw/H.264 capture via scrcpy video, fewer verification captures.
- Observation: the phone had Developer options > diagnosis-type screen foregrounded (`DevelopmentSettingsDashboardActivity`); the earlier `home` keypress returned it to the launcher.
