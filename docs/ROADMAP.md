# Roadmap: effort and impact

Effort: **S** under 1 hour, **M** half a day, **L** several days.
Impact is the effect on time per task, reliability, tokens or safety.

## Scope decisions (what we do not build, and why)

One better solution replaces several ideas. We build the better one only.

| Idea | Decision | Reason |
|---|---|---|
| Parallel screenshot and tree capture | **Dropped** | `observe` no longer takes a screenshot by default. The tree backend (A5) removes the rest. |
| `act([...])` step batching | **Dropped** | Recipes do the same job with checks and a fallback. |
| Intent shortcuts as a separate feature | **Merged** into recipes | An intent is one kind of recipe step. A small `open_url` tool covers it. |
| Hand-off tool for PIN, CAPTCHA, OTP | **Merged** | Tools return `NEEDS_HUMAN:`. No separate tool. |
| `verify=fast` (one screenshot after the touch) | **Dropped** | The video-packet signal (A2) replaces it. We keep `off` and `full`. |
| Video-packet change signal (A2) | **Dropped for now** | `observe` now costs 0.4 to 0.8 s, so asking the screen directly is as cheap as listening to the video stream. Revisit only if fixed waits cause many missed loads. |
| Decode video frames as screenshots | **Deferred** | Only `look()` needs pixels. A2 needs no decoding. |
| Edge-swipe and shade tools | **Dropped** | Key presses already cover back, home and recents. |
| Tool groups and profiles | **Dropped** | Measured: 17 tool definitions cost about 1,500 tokens (now 26 tools, about 2,900). The real cost is the `observe` output on every step. |
| Big architecture rewrite | **Dropped** | Each change was built as a small pure module. One cleanup pass at the end (round 7) moved code without changing the tools. |
| Wireless adb, iOS | **Out of scope** | |

Shared building blocks (built once):

- `state.py`: one adb call gives wake state, lock, app, rotation, keyboard, size. Auto-wake, the banner, and rotation use it.
- `snapshot.py`: stale-index protection, change detection, text lookup, and the element under a tap (for the guard).
- `store.py`: one directory, with size caps. The run log, notes and recipes all use it.

## Matrix

|  | **High impact** | **Medium or low impact** |
|---|---|---|
| **Low effort (S, M)** | **Quick wins. All done.** Snapshot ids, risky-tap guard, lazy screenshot, fixed-wait actions, auto-wake and banner, `tap_text`, run log | **Fill-ins. All done.** `observe` diff, `wait_for`, `open_url`, CI, SECURITY.md |
| **High effort (L)** | **Big bets. Done or dropped.** Fast UI tree (done), recipes (done), video-packet signal (dropped) | **Later. Done.** `look()`, Chrome DevTools. Video-frame screenshots stay deferred. |

## Status

| ID | Item | Effort | Impact | Status |
|---|---|---|---|---|
| C2 | Snapshot ids, stale-tap rejection | S | High | **Done** |
| C1 | Risky-tap guard (buy, pay, send, delete) | S | High | **Done** |
| A4 | Screenshot only on request | S | High | **Done** |
| A1 | `off` mode: fixed 400 ms wait, no checks | S | High | **Done** |
| C3, C4, C6 | Auto-wake, state banner, rotation | M | High | **Done** |
| A8 | `tap_text`, `wait_for` | S | Medium | **Done** |
| A9 | Change report and `diff_only` on `observe` | M | Medium | **Done** |
| C7 | Run log with size cap | S | Medium | **Done** |
| A2 | Video-packet change and settle signal | M | High | **Dropped for now.** Cheap `observe` replaced the need. |
| A5 | Fast UI tree (uiautomator2) | L | High | **Done.** `observe` 3.0-4.5 s to 0.4-0.8 s. Optional extra, automatic fallback. |
| -- | Retest Amazon deep link from a cold start | S | High | **Done. It works.** A link with brand and price filters (`rh=p_123:<brand id>,p_36:-200000`) opened the app on filtered results from a cold start. The brand ids come from the filter panel (Levi's 200356, Jack & Jones 339433). Recipes should use this. |
| B1 | App notes, loaded on request | S | Medium | **Done.** `notes()`. `observe` only says that notes exist. |
| B2 | Recipes (record, replay, stop at first failure) | L | High | **Done.** `record`, `recipes`. Typed text and coordinates are never stored. |
| -- | `open_url` tool | S | Medium | **Done.** Only safe link schemes. |
| -- | `look(question)` small-model plug-in | M | Medium | **Done.** MCP sampling first (asks for a small model), then any OpenAI-compatible endpoint. |
| -- | Chrome DevTools for web pages | L | Medium | **Done.** `web_read` 0.12 s, `web_click` 0.14 s. No install. Guard applies. |
| -- | Real agent end to end | M | High | **Done.** Kiro CLI, 15 runs over 11 apps. See README. |
| -- | Daily tasks for India, safety retest | M | High | **Done.** Guard extended to checkout, pay, UPI, booking. Per-phone lock. |
| -- | Refactor and cleanup | M | Medium | **Done.** Same 26 tools. See HISTORY.md round 7. |
| -- | Warm-up at server start | S | Medium | **Done.** First `observe` 7.6 s to 1.2 s. |

## Open items

| Item | Why it is open |
|---|---|
| Signed-in tasks (UPI history, Gmail, Keep) | No account on the test phone. Not signed in on purpose. |
| Apps not on the test phone (WhatsApp, Swiggy, Zomato, Blinkit, Zepto, IRCTC, cab apps) | Install, then run the 5 tests in [DAILY_APPS_INDIA.md](DAILY_APPS_INDIA.md). |
| Claude Code and Codex as host agents | Not logged in on the test Mac. Only Kiro CLI is tested. |
| A real vision model for `look()` | Tested with a stub model only. Kiro's client does not support MCP sampling. |
| Video-packet change signal | Dropped for now (see above). Revisit if fixed waits miss slow screens. |

Measured results for every round are in [HISTORY.md](HISTORY.md) and the README.
