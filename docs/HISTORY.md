# Build history

How droidpilot got from "no phone visible" to "a real agent does daily tasks". Each round lists what was measured, what broke and what changed. All numbers are from a realme 9 (RMX3521, Android 14, 1080x2400) on USB, unless the row says emulator.

This file replaces the old `FINDINGS.md` and `PERFORMANCE.md`.

## Round 1: setup and first build

**Environment.** macOS 15.7, Intel. Homebrew could not install (a system folder was not writable), so platform-tools 37.0.3 and scrcpy 5.0.1 went to `~/.local/opt`. `env.sh` sets the paths.

**Phone.** The phone was in USB tethering mode, which has no ADB interface. "Diagnosis mode" was not the same as USB debugging. After USB debugging was on, adb saw the phone.

**Key finding: scrcpy gives real multi-touch.** Sources: scrcpy `doc/develop.md`, `ControlMessage.java`, `ControlMessageReader.java`.

- The scrcpy server runs as the `shell` user and injects events with `InputManager.injectInputEvent()`. A socket stays open, so there is no process per event.
- A touch message has an action, a pointer id, a position, the screen size and a pressure. One pointer id per finger gives pinch, rotate and multi-finger swipes.
- The protocol is internal. Client and server versions must match exactly, so droidpilot pins 5.0.1.

**First build.** An MCP server with 18 tools, its own scrcpy control client, a UI tree reader and a screenshot-diff check after each action.

## Round 2: emulator, then the phone

The phone was not ready at first, so a Pixel 6 emulator (Android 14) was installed for testing (`scripts/emulator.sh`).

| Check | Result |
|---|---|
| scrcpy handshake as written from the source | Worked first time |
| Multi-touch | Confirmed: `dumpsys input` showed 3 pointers during a 3-finger hold |
| End-to-end through the real MCP server | 12 of 12 on the emulator, then 12 of 12 on the phone |

**Bug found.** adb inherited the MCP server's stdin and swallowed JSON-RPC messages. Every call after the first hung. Fix: all subprocesses use `stdin=DEVNULL`.

## Round 3: the first real task, and why it was slow

Task: open Amazon, find black jeans from a global brand under 2,000 rupees, add to cart.

| Measure | Value |
|---|---|
| Wall time | about 27 minutes |
| Calls | about 59 |
| Finished | No (0 items in cart) |

Measured cost of each step at that time:

| Step | Time |
|---|---|
| Touch through scrcpy | 0.05 s |
| Touch through `adb shell input tap` | 0.16 s |
| Screenshot (PNG, 2.5 MB over adb) | 1.3 to 1.9 s |
| UI tree dump (`uiautomator dump`) | 2.6 to 3.3 s |
| One tap with screen check | 4.8 to 6.1 s |

The check after the touch took more than 98% of each action.

Other causes:
- No memory of the app.
- The Amazon filter panel is a web view, and Back walks its history. About 12 calls were lost there.
- A stale element index caused a wrong tap.
- The stay-awake setting covered USB power only, and the phone reported AC power, so the screen locked twice.

**Ideas from the user, rated at that time:**
1. A small model for screenshots: good, but not the first bottleneck. This became `look()`.
2. Stored procedures: highest value after speed. These became recipes and notes.
3. Storage cleanup: small. This became `droidpilot clean` and the size caps.
4. Selective loading: tool definitions cost only about 1,500 tokens (17 tools then). The real cost was the `observe` output. This became compaction and diffs.
5. A public repository with a plain README: done.

## Round 4: speed and safety (Phase 0)

| Call | Before | After |
|---|---|---|
| Tap or key press | 4.8 to 6.1 s | 0.41 s |
| Scroll | about 5 s | 0.75 s |
| `observe` | about 5.4 s | 3.0 to 3.9 s |

Changes:
- **Fixed waits.** Actions use a 400 ms wait instead of a screenshot loop. `observe` reports `changed=yes/NO`.
- **Snapshots.** Snapshot ids, and stale taps are rejected.
- **Safety guard.** Buy, pay, send and delete taps return `BLOCKED`.
- **Auto-wake.** A screen with no PIN wakes and unlocks itself.
- **Lookup and logging.** `tap_text` and a run log were added.

**Bug found.** Amazon labels both "Add to cart" and "Buy now" as "Submit". Only the element id names them. Lookup and the guard now read ids.

**First finished task.** Jack & Jones Regular Fit Low Rise, black, 1,439 rupees, was added to the cart. The Amazon deep link with brand and price filters (`rh=p_123:<brand>,p_36:-200000`) was confirmed to work.

## Round 5: fast tree and memory

| Call | Before | After |
|---|---|---|
| `observe` | 3.0 to 4.5 s | 0.4 to 0.8 s |
| First `observe` after start | 7.6 s | 1.2 s (warm-up) |
| Replay of a 2-step recipe | n/a | 3.4 s |

Changes:
- **Fast tree.** An optional uiautomator2 tree takes 0.6 s against 2.7 s. It falls back automatically.
- **Parallel state probe.** The keyboard query, which took 0.65 s alone, now runs only when a text field has focus.
- **Memory and links.** `open_url`, app notes, and recipes with `record`.
- **Chrome DevTools tools.** `web_read` takes 0.12 s and `web_click` 0.14 s.
- **`look()`.** It uses MCP sampling or an OpenAI-compatible endpoint.

**Bug found.** The recipe selector chose "Levi's", which matched two cards. It now prefers text that matches one element only, and skips prices and counts.

## Round 6: a real agent, then daily tasks

Kiro CLI (Claude Sonnet 5.5) drove the phone from one sentence per task. See the README for every run.

Bugs found and fixed:

| Bug | Fix |
|---|---|
| Kiro ignores the MCP servers of an untrusted folder in headless mode | Use `--trust-workspace` |
| The guard missed "Proceed to checkout" and "Proceed to Buy" | Guard covers checkout, pay, UPI, booking, send, post, delete and log out |
| Two agents drove one phone at once (a test mistake) | A per-phone lock |
| The lock locked out its own server (warm-up thread race) | `connect()` is serialized |
| The lock leaked when adb was missing (found by CI) | adb is checked before the lock is taken |
| The status bar made a still screen look changed every minute | The status bar is removed from the tree |
| `tap_text("Wi-Fi")` could not match | One hyphen rule for the query and the screen |

## Round 7: refactor

The code was reorganized. The 26 MCP tools are unchanged (checked by diffing every tool schema before and after).

- **New modules:**
  - `errors.py` (error types)
  - `config.py` (every environment setting)
  - `gestures.py` (pure touch geometry and keycodes)
  - `recorder.py` (recipe recording, replacing module globals)
  - `cli.py` (the command line)
- **`server.py`** now holds tool definitions only. The vision sampling code moved to `vision.py`.
- **Tests** are grouped by module, with shared helpers in `tests/conftest.py`. There are 62 tests, up from 49.
- **Lint and docs:** ruff and pytest are configured in `pyproject.toml`, and lint is clean. The docs were merged: this file replaces `FINDINGS.md` and `PERFORMANCE.md`.

**Bug found during the refactor check.** A device test right after an agent task fell back to single-touch for the whole session. The old server was still shutting down while the new one pushed the same scrcpy jar path. Fixes:
- Each launch uses its own jar name.
- A failed start is retried once.
- After a fallback, scrcpy is tried again after 30 s.
- A new launch deletes jars older than 10 minutes.

**Bug found in `scripts/agent-task.sh`.** It read its results from a hard-coded folder, so another output folder gave wrong results. It now uses `DROIDPILOT_TASK_OUT`, and checks its arguments.

