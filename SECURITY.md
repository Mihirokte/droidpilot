# Security

droidpilot controls a real phone. Treat it like a remote desktop.

- The agent can read the screen and touch anything the user can touch.
- The safety guard stops taps on buy, pay, send and delete buttons. It is a seat belt, not a lock. It reads labels. It does not understand intent.
- The run log (`~/.cache/droidpilot/traces`) stores tool names, arguments and times. It never stores screen content. It replaces typed text with its length.
- Screenshots go to the model that the agent uses. Do not point droidpilot at a phone with data you cannot share with that model.
- Use a test phone or a work profile for risky tasks.
- Do not give an agent a phone with banking apps unlocked.

To report a problem, open a GitHub issue. For a serious flaw, use a private security advisory on GitHub.

## Notes and recipes

- They are plain files in `~/.cache/droidpilot/knowledge`. Anyone with access to your Mac can read them.
- A recipe stores element text and link addresses. A link can hold a search word, so use parameters for private values.
- Typed text is never stored in a recipe. It becomes a parameter that you supply at replay.
- A recipe cannot confirm a buy, pay, send or delete tap.
- `open_url` accepts only http, https, geo, mailto, tel, sms, smsto and market links.
