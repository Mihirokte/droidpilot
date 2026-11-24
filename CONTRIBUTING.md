# Contributing

## Before you start

Read [docs/ROADMAP.md](docs/ROADMAP.md). Some ideas were dropped on purpose, with the reason.

## Where code goes

| Kind of code | Put it in |
|---|---|
| A decision with no I/O (parsing, matching, geometry, rules) | A pure module: `snapshot`, `perception`, `gestures`, `guard`, `state`, `recipes`, `recorder` |
| Talking to the phone (adb, sockets, Chrome) | `phone.py`, `web.py`, `scrcpy.py`, `fasttree.py`, `adb.py` |
| A new MCP tool | `server.py`. Keep the tool a thin call into the controller. |
| A new setting | `config.py`. Read every environment variable there. |
| A new error type | `errors.py` |

## Checks

1. `uv run ruff check src tests` must be clean.
2. `uv run pytest` must pass. No phone is needed.
3. Test pure logic with real captured phone output when you can (see `tests/test_state.py`).
4. If you changed the controller or the server, run `uv run python tests/e2e_device.py` on a phone or the emulator (`scripts/emulator.sh start`).

## Tool descriptions

The agent reads every tool description in every session. Keep them short and exact. Say what the tool returns.
