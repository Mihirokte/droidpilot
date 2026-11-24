# Research synthesis: what to copy, what to beat

Sources are arXiv abstract pages and READMEs fetched in this project's sessions. Numbers are as reported by the authors, not reproduced by us.

## Landscape (verified from abstracts/READMEs)

| Work | What it contributes | Reported result |
|---|---|---|
| DroidBot-GPT (2304.07061) | UI state to text prompt, LLM picks action | 39.4% of 33 tasks |
| AutoDroid (2308.15272) | Functionality-aware UI text + app memory from exploration | 71.3% of 158 tasks |
| AppAgent (2312.13771) | Simple action space (tap/swipe); learns apps by exploration or demonstration into a knowledge base | 50 tasks, 10 apps (qualitative) |
| SeeClick (2401.10935) | Screenshot-only agent; GUI grounding is the bottleneck; ScreenSpot benchmark | grounding gains track agent gains |
| Ferret-UI (2404.05719) | Mobile screens are tall with small targets; "any resolution" split into 2 sub-images | beats GPT-4V on UI basics |
| AndroidWorld (2405.14573) | Parameterised, reproducible tasks with programmatic rewards | 116 tasks, 20 apps; best baseline then 30.6% |
| AndroidControl (2406.03679) | 15,283 demos, 833 apps; fine-tuning scales in-domain, slowly out-of-domain | OOD gain needs more than data |
| Mobile-Agent-v2 (2406.01014) | Planner + decision + reflection agents, memory unit | +30% over single agent |
| OS-Atlas (2410.23218) | Open grounding model, 13M-element corpus | SOTA open grounding then |
| AndroidLab (2410.24024) | 138 tasks, 9 apps; training lifts open models | LLM 4.6% to 21.5% |
| Aguvis (2412.04454) | Pure-vision agent, grounding and planning trained in separate stages | open-source SOTA then |
| UI-TARS (2501.12326) | End-to-end screenshot model, reflective online traces | AndroidWorld 46.6 |
| Mobile-Agent-E (2501.11733) | Persistent **Tips** and **Shortcuts** (reusable action sequences), Action Reflector | +22% abs. over prior SOTA |
| Mobile-Agent-v3 / GUI-Owl (2508.15144) | Self-evolving trajectory data, RL | AndroidWorld 73.3 (66.4 for the 7B model) |
| scrcpy (develop.md, source) | Real input injection + video over a socket; multi-touch via pointerId | n/a |
| uiautomator2 | On-device HTTP service over UiAutomator | n/a |
| mobile-mcp, DroidRun/Mobilerun, Open-AutoGLM | Existing MCP/CLI wrappers, ADB-based | self-reported only |

## Patterns that recur across the strong systems

1. **Reflection after every action.** Mobile-Agent-v2 and -E both add an explicit check of what the action did. droidpilot's version: `observe` reports `changed=yes/NO` and what changed.
2. **Persistent skills from experience.** AppAgent (knowledge base), Mobile-Agent-E (Shortcuts, Tips), AutoDroid (app memory). Nobody ships this as a model-agnostic layer you can bolt onto any coding agent.
3. **Grounding is the weak link for vision-only agents** (SeeClick, Ferret-UI, OS-Atlas, UI-TARS, Aguvis all attack it). An accessibility tree sidesteps grounding where it exists. Both are needed: the tree fails on games, WebViews and Flutter.
4. **Benchmarks use emulators.** AndroidWorld and AndroidLab assume AVDs. Real-device results are rarer, and real phones have OEM quirks (realme permission gate).

## Gap we are filling

Existing agents bundle the model, the loop and the device layer. Here the model is whatever coding agent the user already runs (Claude, Codex, Gemini, Kiro), so the product is the **device layer**: complete touch vocabulary, honest feedback after each action, and memory. The agent's own reasoning supplies planning and reflection.

## Where this went

Each pattern above became a feature. See [HISTORY.md](HISTORY.md) for when and with what result:

- Reflection after every action: `observe` reports `changed=yes/NO` and a diff.
- Persistent skills: `record` and `recipes` (Mobile-Agent-E Shortcuts), `notes` (Tips).
- Grounding: the UI tree first; `look()` and screenshots for tree-less screens.
- Real devices: tested on a realme 9, with its OEM quirks.
