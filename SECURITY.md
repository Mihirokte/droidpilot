# Security

droidpilot controls a real phone. Treat it like a remote desktop.

- The agent can read the screen and touch anything the user can touch.
- The safety guard stops taps on buy, pay, send and delete buttons. It is a seat belt, not a lock. It reads labels. It does not understand intent.
- The run log (`~/.cache/droidpilot/traces`) stores tool names, arguments and times. It never stores screen content. It replaces typed text with its length.
- Screenshots go to the model that the agent uses. Do not point droidpilot at a phone with data you cannot share with that model.
- Use a test phone or a work profile for risky tasks.
- Do not give an agent a phone with banking apps unlocked.

To report a problem, open a GitHub issue. For a serious flaw, use a private security advisory on GitHub.
