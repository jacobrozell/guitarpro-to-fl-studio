#!/usr/bin/env python3
"""Dump every mixer insert's plugin chain (slot state + all param values) to JSON.

Usage: snapshot_chains.py out.json [--tracks 0-25]
build_template.py replays these values onto template plugins by plugin name.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from push_to_fl import call  # noqa: E402


def params(t, s):
    out, start = [], 0
    while start is not None:
        r = call("plugin_get_params", {"track": t, "slot": s, "start": start})
        out += [{"i": p["i"], "name": p["name"], "v": p["v"], "s": p["s"]} for p in r["params"]]
        start = r["next_start"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--tracks", default="0-25")
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.tracks.split("-"))
    names = {t["i"]: t for t in call("mixer_list_tracks", {"start": 0})["tracks"]}
    snap = []
    for t in range(lo, hi + 1):
        slots = call("plugin_list", {"track": t})["slots"]
        if not slots:
            continue
        info = names.get(t) or call("mixer_list_tracks", {"start": t})["tracks"][0]
        snap.append({
            "insert": t, "name": info["name"], "vol_db": info["vol_db"], "pan": info["pan"],
            "routes_to": call("mixer_get_routing", {"track": t})["routes_to"],
            "slots": [{**call("plugin_get_slot", {"track": t, "slot": s["slot"]}), "plugin": s["name"],
                       "params": params(t, s["slot"])} for s in slots],
        })
        print(f"ins {t} {info['name']}: " + ", ".join(
            f"{x['plugin']}{' (muted)' if x['muted'] else ''}" for x in snap[-1]["slots"]))
    a.out.write_text(json.dumps(snap, indent=1))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
