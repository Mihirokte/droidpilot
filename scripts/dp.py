"""Tiny CLI over droidpilot.Phone for manual/agent driving: uv run python scripts/dp.py <cmd> [args]"""
import json, sys
from droidpilot.phone import Phone

p = Phone()
cmd, *a = sys.argv[1:]
if cmd == "observe":
    p.grab(); print(p.refresh_ui())
    json.dump({e.index: p.geo.to_view(*e.center) for e in p.elements}, open("/tmp/dp_last.json", "w"))
    print("app:", p.current_app())
elif cmd == "tap_element":
    p.grab(); x, y = json.load(open("/tmp/dp_last.json"))[a[0]]; print(p.tap(x, y))  # centers from the last observe
elif cmd == "tap_text": print(p.tap_text(a[0], int(a[1]) if len(a) > 1 else 0, "confirm" in a))
elif cmd == "wait_for": print(p.wait_for(a[0], int(a[1]) if len(a) > 1 else 5000))
elif cmd == "tap": p.grab(); print(p.tap(float(a[0]), float(a[1])))
elif cmd == "type": p.grab(); print(p.type_text(a[0], submit=len(a) > 1 and a[1] == "submit"))
elif cmd == "key": p.grab(); print(p.press_key(a[0]))
elif cmd == "scroll": p.grab(); print(p.scroll(a[0], float(a[1]) if len(a) > 1 else 0.5))
elif cmd == "open": p.grab(); print(p.open_app(a[0]))
elif cmd == "apps": print("\n".join(x for x in p.list_apps(True) if not a or a[0] in x))
elif cmd == "shot": open(a[0], "wb").write(p.screenshot_jpeg()); print("saved", a[0])
p.close()
