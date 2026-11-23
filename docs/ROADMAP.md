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
| Tool groups and profiles | **Dropped** | Measured: all 17 tool definitions cost about 1,500 tokens. The real cost is the `observe` output. |
| Big architecture rewrite | **Dropped** | Each change is built as a small pure module. No second rewrite. |
| Wireless adb, iOS | **Out of scope** | |

Shared building blocks (built once):

- `state.py`: one adb call gives wake state, lock, app, rotation, keyboard, size. Auto-wake, the banner, and rotation use it.
- `snapshot.py`: stale-index protection, change detection, text lookup, and the element under a tap (for the guard).
- `store.py`: one directory, with size caps. The run log, notes and recipes all use it.

## Matrix

|  | **High impact** | **Medium or low impact** |
|---|---|---|
| **Low effort (S, M)** | **Quick wins. Done.** Snapshot ids, risky-tap guard, lazy screenshot, fixed-wait actions, auto-wake and banner, `tap_text`, run log | **Fill-ins.** `observe` diff (done), `wait_for` (done), `open_url` (S, next), CI and SECURITY.md (done) |
| **High effort (L)** | **Big bets.** Fast UI tree (A5), video-packet change signal (A2), recipes | **Later.** `look()` with a small model, Chrome DevTools for web pages, video-frame screenshots |

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
| -- | Real agent end to end | M | High | **Done.** Kiro CLI, 3 tasks, all correct. See README. |
| -- | Warm-up at server start | S | Medium | **Done.** First `observe` 7.6 s to 1.2 s. |

## Measured effect of the first batch (realme 9)

| Call | Before | After |
|---|---|---|
| Key press or tap | 4.8 to 6.1 s (checked) | **0.41 s** |
| `tap_text` | observe + tap, two calls | **0.23 to 0.46 s**, one call |
| Scroll | about 5 s | **0.75 s** |
| `observe` | about 5.4 s (tree + screenshot + app name) | **3.0 to 3.9 s** (tree only) |
| Start from a locked, asleep phone | manual, failed twice | automatic |

`observe` is now limited by the UI dump (2.7 s floor). That is A5.

Not measured: the end-to-end time of the Amazon task after these changes. We should run it again after A5.

## Measured effect of the second batch (realme 9)

| Call | Before | After |
|---|---|---|
| `observe` | 3.0 to 4.5 s | **0.4 to 0.8 s** (one-time server start: about 2.3 s) |
| State probe | 0.98 s, run first | runs at the same time as the tree dump. The keyboard query (0.65 s) now runs only when a text field has focus. |
| Replay of a recorded 2-step recipe | n/a | 3.4 s, with new parameters |

The fast tree needs `pip install 'droidpilot[fast]'`. It installs no app on the phone. It pushes `u2.jar` to `/data/local/tmp`. `droidpilot clean` removes it.

## Live task result

Task: put a black pair of jeans from a global brand, under 2,000 rupees, in the Amazon cart. No order.

- Result: **done**. Cart holds Jack & Jones Men's Regular Fit Low Rise Black Jeans, 1,439 rupees, size 30W/32L, quantity 1. Nothing was ordered.
- Levi's 511 in Black was found at 1,704 rupees, but only size 28 was in stock.
- With the deep link and the new tools, the search took 4 calls. The first attempt took about 59 calls and did not finish.
- Two bugs found by the live run and fixed: (1) Amazon names its add-to-cart and buy buttons "Submit". Only the element id says what they do. Lookup and the guard now read the id too. (2) The guard now names the element it blocked.
- The live guard test refused a tap on the Buy button.

## Agent runs (Kiro CLI, Claude Sonnet 5.5)

| Task | Wall time | Calls | Tool time | Result |
|---|---|---|---|---|
| Android version in Settings | 32 s | 6 | 9.7 s | Correct |
| Weather in Chrome | 31 s | 4 | 8.1 s | Correct. The agent chose `open_url` itself. |
| Amazon cart read + jeans search, no changes | 98 s | 17 | 27.4 s | Correct. Cart unchanged. |

Most of the wall time is now the model, not the phone.

Findings from these runs, all fixed:
- Kiro skips the MCP servers of an untrusted folder in headless mode. Use `--trust-workspace`.
- The run log hid the text of every `tap_text`. Now it hides only typed text and form values.
- The agent used screenshots on a Chrome page. `observe` now says that `web_read` is faster there.
- The first `observe` paid 7.6 s to start the fast tree server. The server now starts it in the background.

## Not done, on purpose

- No model is bundled. `look` uses the host or an endpoint you choose.
- No iOS. No wireless adb.
- The video-packet change signal stays dropped. `observe` is cheap enough.
