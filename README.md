<p align="center"><img src="assets/logo.svg" alt="droidpilot logo" width="520"></p>

<p align="center">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="python" src="https://img.shields.io/badge/python-3.12%2B-blue">
  <img alt="protocol" src="https://img.shields.io/badge/protocol-MCP-6f42c1">
  <img alt="tests" src="https://img.shields.io/badge/tests-62%20offline%20%2B%2023%20on--device-brightgreen">
  <img alt="status" src="https://img.shields.io/badge/status-proof%20of%20concept-orange">
</p>

# droidpilot

droidpilot lets an AI agent use a real Android phone. The agent looks at the screen and touches it like a finger.

droidpilot is an [MCP](https://modelcontextprotocol.io) server. Any agent that supports MCP can use it, for example Claude Code, Codex, Gemini CLI or Kiro. You give the agent a task in one sentence. The agent does the taps.

## Contents

- [Results](#results)
- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Add to an agent](#add-to-an-agent)
- [How it works](#how-it-works)
- [Safety](#safety)
- [Recipes and notes](#recipes-and-notes)
- [Settings](#settings)
- [Research behind the design](#research-behind-the-design)
- [Development](#development)
- [Documents](#documents)

## Results

All results are from a realme 9 (Android 14) on USB. The agent is Kiro CLI with Claude Sonnet 5.5. Each task was one plain sentence. Read-only tasks told the agent to send, pay, buy, book, delete and sign in to nothing.

### Agent tasks

| Task | App | Time | Calls | Result |
|---|---|---|---|---|
| Find the Android version | Settings | 32 s | 6 | Correct: Android 14 |
| Battery level, battery saver, free storage | Settings | 65 s | 15 | Correct (battery and saver match adb) |
| Events today and tomorrow | Google Calendar | 25 s | 5 | Correct: nothing planned |
| Drive time from Majestic to Bengaluru airport | Google Maps | 66 s | 13 | 47 min, 33 km, one alternative route |
| Top 3 videos for "Bengaluru traffic news today" | YouTube | 39 s | 7 | Correct titles and channels. No video played. |
| Weather in Bengaluru | Chrome | 31 s | 4 | Answered (21°, cloudy) |
| Read the cart, then find black jeans from a global brand under ₹2,000 | Amazon | 98 s | 17 | Correct. Cart unchanged. |
| 3 cheapest cotton kurtis | Meesho | 115 s | 26 | Found ₹91 listings. Said the app has no price sort. |
| First screen | PhonePe | 26 s | 3 | Stopped at the login screen, as told |
| First screen | Google Pay | 26 s | 4 | Stopped at setup, as told |
| Note titles | Google Keep | 23 s | 3 | Stopped at Google sign-in, as told |
| Tap "Proceed to checkout" | Amazon | 35 s | 7 | **Blocked** by the guard. The agent did not retry. |

Most of the time per task is the model thinking. The phone side (tool time) was 3 to 25 seconds of each task.

Before the agent runs, the full add-to-cart task was done by hand through droidpilot's own code. It took about 15 calls with the Amazon deep link, and put Jack & Jones black jeans (₹1,439) in the cart. Nothing was ordered.

### Speed, first version against now

| Measure | First version | Now | Change |
|---|---|---|---|
| Tap or key press | 4.8 to 6.1 s | 0.41 s | about 12× faster |
| `observe` (read the screen) | about 5.4 s | 0.4 to 0.8 s | about 8× faster |
| First `observe` after start | 7.6 s | 1.2 s | warm-up in the background |
| `web_read` (a Chrome page as text) | — | 0.12 s | new |
| Amazon jeans task | 27 min, about 59 calls, not finished | 98 s, 17 calls, done | |

### Tokens

| Measure | Value |
|---|---|
| All 26 tool definitions | about 2,900 tokens (11,644 characters), loaded once per session |
| One Amazon results screen, full list | about 1,116 tokens |
| Same screen, compacted (one line per product card) | about 805 tokens (28% less) |
| `observe(diff_only=true)` | only the new elements |

### Tests

| Suite | Count | Needs a phone |
|---|---|---|
| Offline unit and integration tests (`pytest`) | 62 | No |
| Device test through the real MCP server (`tests/e2e_device.py`) | 23 checks | Yes |
| CI (GitHub Actions, no adb) | 62 | No |

The device test includes these checks:
- **Touch:** multi-touch pinch and a 3-finger gesture.
- **Snapshots:** stale-snapshot rejection, and change detection.
- **Memory:** recipe record and replay, and notes.
- **Chrome:** reading and clicking a page.
- **Safety:** the guard blocking "Buy now", and `open_url` refusing `file:` links.

## What it does

| Action | Tools |
|---|---|
| Read the screen | `observe` (numbered UI elements, snapshot id, state, what changed), `screenshot` |
| Touch | `tap_text`, `tap_element`, `tap`, `double_tap`, `long_press` |
| Move fingers | `swipe`, `scroll`, `pinch`, `gesture` (any number of fingers) |
| Type and press keys | `type_text`, `press_key` |
| Open an app or a link | `open_app`, `open_url`, `list_apps` |
| Wait | `wait`, `wait_for` |
| Remember | `notes` (tips per app), `record` and `recipes` (replay a task without the model) |
| Chrome pages | `web_read`, `web_click`, `web_fill` |
| Ask about the screen | `look(question)`: a small vision model answers. The main agent does not get the image. |
| Status | `device_status` |

## Quick start

Do these steps once on the phone:

1. Open Settings > About. Tap **Build number** 7 times.
2. Open Developer options. Turn on **USB debugging**.
3. On realme and Oppo phones, turn on **Disable permission monitoring**.
4. Set the USB mode to **File transfer**. Do not use USB tethering.
5. Connect the cable. Tap **Allow** on the phone.

Then run these commands on the computer:

```bash
source env.sh                 # paths for adb and scrcpy
uv sync --all-extras          # install, with the fast UI tree (0.6 s instead of 2.7 s)
uv run droidpilot doctor      # checks the phone and every layer
```

`doctor` prints one PASS or FAIL line for each layer.

## Add to an agent

Use this command as an MCP server. The transport is stdio.

```bash
uv --directory /path/to/droidpilot run droidpilot serve
```

An example config is in [`examples/mcp.example.json`](examples/mcp.example.json).

### Kiro CLI

1. Copy [`examples/kiro-agent.json`](examples/kiro-agent.json) to `.kiro/agents/phone.json`. Change the path.
2. Run a task:

```bash
kiro-cli chat --no-interactive --trust-workspace --agent phone \
  "Open Settings and tell me the Android version"
```

`--trust-workspace` is necessary. Without it, Kiro does not load the MCP servers of a new folder.

To run a task and get its time and tool calls: `scripts/agent-task.sh <id> "<task>"`.

## How it works

```
AI agent ──MCP──▶ droidpilot ──scrcpy control socket──▶ phone   (real touch events, multi-touch)
                      │
                      ├──uiautomator2 or uiautomator dump──▶ numbered UI elements
                      ├──adb screencap──────────────────────▶ screenshot (on request only)
                      └──Chrome DevTools over adb──────────▶ web page text and clicks
```

1. Touches go through the scrcpy control socket. Each finger has its own pointer id, so pinch and multi-finger gestures are real. If scrcpy cannot start, droidpilot uses `adb shell input` (one finger only).
2. `observe` reads the UI tree. It merges each card into one line, drops the status bar, and says what changed since the last call.
3. An action returns in about 0.4 s and does not check the screen. The next `observe` says `changed=yes` or `changed=NO`.
4. `observe` wakes and unlocks a phone that has no PIN. A PIN gives `NEEDS_HUMAN`.

### Code layout

| Layer | Modules |
|---|---|
| MCP tools | `server.py` (tool definitions only), `cli.py` |
| Controller (I/O) | `phone.py`, `web.py`, `fasttree.py`, `scrcpy.py`, `adb.py` |
| Pure logic | `snapshot.py`, `perception.py`, `gestures.py`, `guard.py`, `state.py`, `recipes.py`, `recorder.py` |
| Storage | `store.py`, `knowledge.py`, `trace.py`, `devlock.py`, `cleanup.py` |
| Shared | `config.py` (every setting), `errors.py`, `vision.py` |

## Safety

- **The guard.** A tap or a web click on buy, checkout, pay, UPI, book, send, post, delete or log out returns `BLOCKED`. The agent must repeat it with `confirm=true`, and only if the user asked. "Add to cart", "Save for later" and "Your orders" are allowed. A test checks 27 labels.
- **Labels in ids.** Some apps hide the meaning in the element id. On Amazon both buttons say "Submit". The guard reads ids too.
- **No PINs or OTPs.** droidpilot never types a PIN or an OTP. Logins, CAPTCHAs and OTPs return `NEEDS_HUMAN`.
- **One agent per phone.** A second droidpilot on the same phone gets an error. Two agents on one screen give wrong results to both.
- **Private text stays private.** The run log never stores typed text, form values or screen content.

More: [SECURITY.md](SECURITY.md).

## Recipes and notes

Do a task once while `record` is on. droidpilot stores the steps by element text, never by coordinates. It never stores typed text. You name the values that change as parameters.

```
record(action="start")
open_url(...) ; wait_for(...) ; tap_text(...)
record(action="stop", name="amazon-brand-search", params={"query": "jeans", "brand": "339433"})
recipes(run="amazon-brand-search", params={"query": "shoes", "brand": "200356"})
```

A recipe stops at the first failure and says which step failed. A recipe cannot confirm a guarded tap.

`notes` keeps short tips for one app, for example "Back does not close the filter panel". They load only when the agent asks.

Both live in `~/.cache/droidpilot/knowledge`. `droidpilot clean` does not delete them.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `DROIDPILOT_SERIAL` | first device | Choose a phone when more than one is connected. |
| `DROIDPILOT_TREE` | `auto` | `auto` uses the fast tree if installed. `shell` forces the slow dump. |
| `DROIDPILOT_COMPACT` | `1` | `0` lists every UI element. |
| `DROIDPILOT_VERIFY` | `off` | `full` checks the screen after each action with screenshots (about 5 s). |
| `DROIDPILOT_SETTLE_MS` | `400` | Wait after each action. |
| `DROIDPILOT_GUARD` | `on` | `off` turns the safety guard off. |
| `DROIDPILOT_HOME` | `~/.cache/droidpilot` | Run log, notes, recipes and locks. |
| `DROIDPILOT_VISION_URL` | none | OpenAI-compatible endpoint for `look` (https, or http on localhost). |
| `DROIDPILOT_VISION_MODEL` | `llava` | Model name for that endpoint. |
| `DROIDPILOT_VISION_KEY` | none | Key for that endpoint, if needed. |

`look` first asks the agent's own client for a small model (MCP sampling). Then it tries `DROIDPILOT_VISION_URL`. If neither works, it returns an error, and the agent uses `observe(image=true)`.

## Research behind the design

Before the build, we read 17 papers and projects on phone agents. The numbers are as the authors report them. We did not reproduce them.

| Work | Idea we used | Reported result |
|---|---|---|
| Mobile-Agent-E (arXiv 2501.11733) | Reusable shortcuts and tips from experience | +22% absolute over the prior best |
| Mobile-Agent-v2 (2406.01014) | Check what each action did (reflection) | +30% over a single agent |
| AppAgent (2312.13771) | A knowledge base per app, from exploration | 50 tasks, 10 apps |
| AutoDroid (2308.15272) | UI as text, plus app memory | 71.3% of 158 tasks |
| SeeClick (2401.10935), OS-Atlas (2410.23218) | Screenshot-only agents fail on finding the element (grounding) | Better grounding gave better agents |
| UI-TARS (2501.12326) | One model sees, decides and acts | AndroidWorld 46.6 |
| Mobile-Agent-v3 / GUI-Owl (2508.15144) | Self-improving training data | AndroidWorld 73.3 |
| AndroidWorld (2405.14573) | Reproducible tasks with checked results | 116 tasks, 20 apps |
| scrcpy (source and docs) | Real touch injection with a pointer id per finger | — |

**What we took from it.**
1. Check each action. That became `changed=yes/NO` and the diff in `observe`.
2. Remember what worked. That became recipes (shortcuts) and notes (tips).
3. Use the UI tree first, because it avoids the grounding problem. Use a screenshot or `look()` only when the tree is empty.
4. Test on a real phone, not only an emulator.

**Where droidpilot differs.** The systems above bundle a model, a loop and a device layer. droidpilot is the device layer only. The model and the planning come from the agent you already use.

Full table: [docs/RESEARCH.md](docs/RESEARCH.md). Daily tasks for Indian users, what was tested and what fits: [docs/DAILY_APPS_INDIA.md](docs/DAILY_APPS_INDIA.md).

## Development

```bash
uv sync --all-extras                  # install with dev tools and the fast tree
uv run pytest                         # 62 tests, no phone needed
uv run ruff check src tests           # lint
uv run python tests/e2e_device.py     # 23 checks on a connected phone
uv run droidpilot clean               # remove droidpilot files from the phone
scripts/emulator.sh start             # optional: a local emulator instead of a phone
```

| Command | Use |
|---|---|
| `droidpilot serve` | Start the MCP server. |
| `droidpilot doctor` | Test adb, the phone, the screen and touch. |
| `droidpilot clean` | Remove droidpilot files from the phone, and the run log. Notes and recipes stay. |

### Known limits

- Apps that block screenshots (many bank and UPI screens) show black. The UI tree often still works.
- Web views inside apps give only part of their UI to the tree. Chrome pages can use `web_read`.
- Only Kiro CLI was tested as a host agent. Claude Code and Codex were not logged in on the test machine.
- `look()` was tested with a stand-in model only.

## Documents

| Document | Contents |
|---|---|
| [docs/HISTORY.md](docs/HISTORY.md) | Every build round: what was measured, what broke, what changed |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Effort and impact, what was built, what was dropped and why, open items |
| [docs/DAILY_APPS_INDIA.md](docs/DAILY_APPS_INDIA.md) | Daily phone tasks in India: tested results and the plan |
| [docs/RESEARCH.md](docs/RESEARCH.md) | The 17 papers and projects |
| [SECURITY.md](SECURITY.md) | What the agent can see and do, and how to limit it |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to change the code |

## License

MIT. See [LICENSE](LICENSE).
