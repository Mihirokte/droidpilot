<p align="center"><img src="assets/logo.svg" alt="droidpilot logo" width="520"></p>

<p align="center">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="python" src="https://img.shields.io/badge/python-3.12%2B-blue">
  <img alt="protocol" src="https://img.shields.io/badge/protocol-MCP-6f42c1">
  <img alt="status" src="https://img.shields.io/badge/status-proof%20of%20concept-orange">
</p>

# droidpilot

droidpilot lets an AI coding agent use a real Android phone. The agent looks at the screen and touches it like a finger.

droidpilot is an [MCP](https://modelcontextprotocol.io) server. Any agent that supports MCP can use it. Examples: Claude Code, Codex, Gemini CLI, Kiro.

## What it does

| Action | Tool |
|---|---|
| Look at the screen | `observe` (UI list, snapshot id, state), `screenshot` |
| Touch | `tap_text`, `tap_element`, `tap`, `double_tap`, `long_press` |
| Move a finger | `swipe`, `scroll` |
| Use two or more fingers | `pinch`, `gesture` |
| Type and press keys | `type_text`, `press_key` |
| Open an app or a link | `open_app`, `open_url`, `list_apps` |
| Wait | `wait`, `wait_for` |
| Remember | `notes` (tips per app), `record` and `recipes` (replay a task without the model) |

An action returns in about 0.4 seconds. It does not check the screen. The next `observe` says `changed=yes` or `changed=NO`. The agent can then find a tap that did nothing.

`observe` also wakes and unlocks a phone that has no PIN. If a PIN blocks it, the result starts with `NEEDS_HUMAN`.

A tap on a buy, pay, send or delete button returns `BLOCKED`. The agent must repeat it with `confirm=true`.

## How it works

```
AI agent  --MCP-->  droidpilot  --scrcpy control socket-->  phone (real touch events)
                        |
                        +--adb screencap + uiautomator-->  screenshot + numbered UI elements
```

1. droidpilot sends touch events through the scrcpy control socket. This gives real multi-touch.
2. If scrcpy fails, droidpilot uses `adb shell input`. This gives one finger only.
3. droidpilot reads the screen with `screencap` and `uiautomator dump`.

## Recipes and notes

Do a task once while `record` is on. droidpilot stores the steps by element text, never by coordinates. It never stores typed text. You name the values that change (for example the search words) as parameters.

```
record(action="start")
open_url(...) ; wait_for(...) ; tap_text(...)
record(action="stop", name="amazon-brand-search", params={"query": "jeans", "brand": "339433"})
recipes(run="amazon-brand-search", params={"query": "shoes", "brand": "200356"})
```

A recipe stops at the first failure and tells the agent which step failed. A recipe cannot confirm a buy, pay, send or delete tap.

`notes` keeps short tips for one app, for example "Back does not close the filter panel". They load only when the agent asks.

Both live in `~/.cache/droidpilot/knowledge`. `droidpilot clean` does not delete them.

## Quick start

Do these steps once on the phone:

1. Open Settings > About. Tap **Build number** 7 times.
2. Open Developer options. Turn on **USB debugging**.
3. On realme and Oppo phones, turn on **Disable permission monitoring**.
4. Set the USB mode to **File transfer**. Do not use USB tethering.
5. Connect the cable. Tap **Allow** on the phone.

Then run these commands on the computer:

```bash
source env.sh               # sets the paths for adb and scrcpy
uv run droidpilot doctor    # checks the phone and every layer
uv sync --extra fast        # optional: faster UI tree (0.6 s instead of 2.7 s)
uv run droidpilot serve     # starts the MCP server
```

## Add to an agent

Use this command as the MCP server. The transport is stdio.

```bash
uv --directory /path/to/droidpilot run droidpilot serve
```

An example config is in [`examples/mcp.example.json`](examples/mcp.example.json).

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `DROIDPILOT_VERIFY` | `off` | `full` checks the screen after each action with screenshots. It is slow (about 5 seconds). |
| `DROIDPILOT_SETTLE_MS` | `400` | Wait after each action. |
| `DROIDPILOT_GUARD` | `on` | `off` turns the safety guard off. |
| `DROIDPILOT_COMPACT` | `1` | `0` lists every UI element. |
| `DROIDPILOT_TREE` | `auto` | `shell` forces the slow dump. `u2` requires the fast one. `auto` uses the fast one if installed. |
| `DROIDPILOT_SERIAL` | first device | Choose a phone when more than one is connected. |
| `DROIDPILOT_HOME` | `~/.cache/droidpilot` | Where the run log is kept. |

## Commands

| Command | Use |
|---|---|
| `droidpilot serve` | Start the MCP server. |
| `droidpilot doctor` | Test adb, the phone, the screen, and touch. |
| `droidpilot clean` | Remove the files droidpilot put on the phone. |

## Test

```bash
uv run pytest                       # no phone needed
uv run python tests/e2e_device.py   # needs a phone or an emulator
```

## Known limits

- `observe` takes 0.4 to 0.8 seconds with the optional fast tree, and 3 to 4.5 seconds without it. See [docs/ROADMAP.md](docs/ROADMAP.md).
- Apps that block screenshots show a black screen. The UI tree can still work.
- Web views inside apps give only part of their UI to the tree.
- A phone without a PIN is easy to use. A phone with a PIN needs the user to unlock it.

## Documents

- [Roadmap: effort, impact, and what we dropped](docs/ROADMAP.md)
- [Performance numbers](docs/PERFORMANCE.md)
- [Security](SECURITY.md)
- [Research summary](docs/RESEARCH.md)
- [Findings log](docs/FINDINGS.md)

## License

MIT. See [LICENSE](LICENSE).
