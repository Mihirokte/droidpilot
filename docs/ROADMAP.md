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
| A2 | Video-packet change and settle signal | M | High | Next |
| A5 | Fast UI tree (uiautomator2 spike first) | L | High | Next. Spike first. |
| -- | Retest Amazon deep link from a cold start | S | Unknown | Next |
| B1 | App notes, loaded by foreground app | S | Medium | After A5 |
| B2 | Recipes (record, replay, diverge to the agent) | L | High | After B1 and C7 |
| -- | `open_url` tool | S | Medium | With B2 |
| -- | `look(question)` small-model plug-in | M | Medium | Later |
| -- | Chrome DevTools for web pages | L | Medium | Later |

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
