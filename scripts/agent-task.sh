#!/bin/zsh
# Run one read-only task with the Kiro agent in .kiro/agents/phone.json, then print time and tool calls.
# usage: scripts/agent-task.sh <id> "<task>"
# Run one task at a time: only one agent can drive a phone.
cd "$(dirname "$0")/.."; source env.sh
OUT=${DROIDPILOT_TASK_OUT:-/tmp/droidpilot-tasks}; mkdir -p "$OUT"
adb shell input keyevent 3 >/dev/null; : > ~/.cache/droidpilot/traces/trace.jsonl
start=$(date +%s)
kiro-cli chat --no-interactive --trust-workspace --require-mcp-startup --agent phone --model claude-sonnet-5.5 "$2 Do not send, pay, buy, book, delete, post or sign in to anything. If a step would do one of those, stop and tell me." > $OUT/$1.log 2>&1
code=$?; wall=$(( $(date +%s) - start ))
cp ~/.cache/droidpilot/traces/trace.jsonl $OUT/$1.trace.jsonl
python3 - "$1" "$wall" "$code" "$OUT" <<'PY'
import json, sys
tid, wall, code, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
rows = [json.loads(l) for l in open(f"$OUT/{tid}.trace.jsonl")]
tools = {}
for r in rows: tools[r["tool"]] = tools.get(r["tool"], 0) + 1
bad = [r for r in rows if r["status"] != "ok"]
print(f"[{tid}] exit={code} wall={wall}s calls={len(rows)} tool_time={sum(r['ms'] for r in rows)/1000:.1f}s non_ok={[(r['tool'], r['status']) for r in bad]}")
print("   tools:", tools)
PY
grep -vE "^\[INFO\]|^\s*$|Tool Load|status: |^\[tool\]|^I'll|^Let me" $OUT/$1.log | tail -6 | cut -c1-240 | sed 's/^/   > /'
