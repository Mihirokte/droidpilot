# Contributing

1. Run `uv run pytest`. All tests must pass. No phone is needed.
2. Put decisions in pure modules (`snapshot`, `guard`, `state`, `perception`). Put adb and sockets in `phone.py` and `scrcpy.py`.
3. Test pure logic with real captured output when you can.
4. Run `uv run python tests/e2e_device.py` if you changed the controller or the server. It needs a phone or the emulator (`scripts/emulator.sh start`).
5. Keep tool descriptions short. Every tool costs the agent context.
6. Read `docs/ROADMAP.md` before you start. Some ideas are dropped on purpose.
