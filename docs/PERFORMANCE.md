# Performance and improvement plan

> **Status:** this file is the first-day baseline and the original analysis. The current numbers are in the README ("Results with a real agent") and in [ROADMAP.md](ROADMAP.md).
>
> | Measure | Day 1 | Now |
> |---|---|---|
> | Tap or key press | 4.8 to 6.1 s | 0.41 s |
> | `observe` | about 5.4 s | 0.4 to 0.8 s (first call 1.2 s) |
> | Amazon jeans task | 27 min, about 59 calls, not finished | 98 s, 17 calls, done by a real agent |

Device: realme 9 (Android 14, 1080x2400), USB cable. Tool: droidpilot 0.1.

## 1. First real task: what happened

Task: open Amazon, find black jeans from a global brand under 2000 rupees, put them in the cart.

| Item | Value | Source |
|---|---|---|
| Wall time | about 27 minutes (phone clock 21:52 to 22:19) | measured |
| Shell calls | about 59 | counted from the session |
| Average per call | about 27 seconds | calculated |
| Items in the cart at the end | 0 | the task was not finished |
| Best candidates found | Levi's 511 Slim, Black, 1,120 rupees (only size 28 in stock); Jack & Jones Regular Fit, 1,154 rupees (colour not checked) | read from the UI tree |

### Why it was slow

| Cause | Effect |
|---|---|
| Every action is checked with 3 or more screenshots | 4.7 s per action, but the touch takes 0.05 s |
| Each shell call started a new process and a new scrcpy server | about 1 s extra per call |
| The agent had no memory of the app | It explored filters, a location pop-up and size stock by trial |
| Amazon search is a web view | Filter panel state is not in the UI tree. The Back key walks the filter history. About 12 calls were lost here. |
| One bug in the helper script | Stale element index caused a wrong tap |
| Stay-awake setting covered USB power only | The phone locked twice. It reported AC power. |
| Sponsored ads at the top of results | Extra scrolling |
| The agent read text only | It never looked at a screenshot, so it could not see the panel state |

## 2. Measured cost of each step

| Step | Time |
|---|---|
| Touch through scrcpy | 0.05 s |
| Touch through `adb shell input tap` | 0.16 s |
| Start the scrcpy server (once per session) | 0.96 s |
| Screenshot (PNG, 2.5 MB over adb) | 1.3 to 1.9 s |
| UI tree dump (`uiautomator`) | 2.6 to 3.3 s |
| Foreground app name (`dumpsys`) | 0.22 s |
| One tap with screen check | 4.8 to 6.1 s |
| One CLI call (start-up + connect + server + checked key) | 10.0 s |

The check after the touch uses more than 98% of the time of an action.

## 3. Your five ideas, rated

### 1. Smaller, faster model for screenshots

- Good idea, but it is not the first bottleneck. The agent read no screenshot in this run. Capture and checking took the time.
- Do this first: make the UI tree the main input. Use a screenshot only when the tree is empty or unclear.
- Then add a tool `look(question)`. A small vision model answers the question in one short sentence. The main agent never receives the image. This keeps the main context small.
- The small model can be local (for example UI-TARS or OS-Atlas class) or a small hosted model. MCP cannot choose the host model. droidpilot must call its own model.
- Cost: an API key or a local model download. Status: not built, not measured.

### 2. Store known procedures ("skills")

- Best value after the speed fix. The same research idea appears in Mobile-Agent-E (Shortcuts and Tips) and AppAgent (knowledge base). See `docs/RESEARCH.md`.
- Keep one small file per app. Example for Amazon: "A location pop-up can appear. Choose *Enter an Indian pincode*, then *Apply*." "Do not use Back to close the filter panel."
- Store steps with resource IDs and text, not with screen coordinates.
- Store only the notes for the current app. Load them when `observe` sees that package.
- Not built yet.

### 3. Storage cleanup

Measured:

| Place | Size | Action |
|---|---|---|
| Phone: `/data/local/tmp/droidpilot-scrcpy-server.jar` | 0.7 MB | `droidpilot clean` removes it |
| Phone: adb port forwards | 0 after use | `droidpilot clean` removes any left |
| Mac: temp files in `/tmp` | under 1 MB | `droidpilot clean` removes them |
| Mac: screenshots | 0 (kept in memory only) | none needed |
| Mac: emulator stack (SDK 6.3 GB, AVD 1.3 GB, JDK 0.3 GB) | 7.9 GB | Reported only. The user decides. |

Built: `droidpilot clean`. A size limit for the future skill store is still needed.

### 4. Clean architecture and selective loading

Built: observe output merges the text of each product card into one line. On one live Amazon screen: 52 elements became 34, and about 1,116 tokens became about 805 (28% less). A unit test covers it.

Still to do:

- Split the 18 tools into groups. Load only `core` (observe, tap, scroll, type, keys, open app) by default. Load `advanced` (pinch, gesture) on request.
- Shorten tool descriptions.
- Return a short diff ("2 elements changed") instead of a full tree after each action.
- Keep the layers separate: device, perception, actions, server. This is already true in the code.

### 5. Public repo with simple README

Done in this session. See the repository README. The README follows ASD-STE100 rules: short sentences, active voice, one instruction per sentence.

## 4. Ranked plan by expected time saved

| Rank | Change | Expected effect | Evidence |
|---|---|---|---|
| 1 | Make the check cheap: one capture of 100 ms thumbnail or a scrcpy video frame, with `verify=off/fast/full` | An action from about 5 s to under 1 s | Measured: touch 0.05 s, check 4.7 s |
| 2 | Keep one long-running server. Do not start a new process per call | Saves about 1 s per call | Measured |
| 3 | Open results with a deep link instead of the filter UI | One call replaces about 25 calls on Amazon | Not tested. The tree showed URLs such as `rh=p_123:200356,p_36:-280000` (brand and price filter). |
| 4 | App notes (skills) | Fewer wrong turns | Research, not measured here |
| 5 | Compact tree plus diff output | 28% fewer tokens now, more with diffs | Measured once |
| 6 | `look(question)` with a small vision model | Fewer blind steps in web views | Not measured |
| 7 | Capture through the scrcpy video stream instead of `screencap` | Frames in tens of ms | Not tested |

## 5. What is not proven

- Rank 3 (deep links) and rank 7 (video capture) are ideas. No test was run.
- Time per call includes the model's thinking time, which droidpilot cannot measure.
- All numbers come from one phone and one app.
