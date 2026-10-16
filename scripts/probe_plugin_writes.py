#!/usr/bin/env python3
"""Find which plugin-param write method FL actually honors.

For each mixer plugin found (or one --target track:slot:param), nudge a param
with each write method, wait, read back, then restore the original value.
Needs FL open with the project loaded and the patched controller reloaded.

Usage: probe_plugin_writes.py [--tracks 0-6] [--params 3] [--target 2:0:5]
"""
import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from push_to_fl import call  # noqa: E402

METHODS = ["plain", "pim_none", "pim_always", "rec"]


def read(t, s, i):
    return call("plugin_get_param", {"track": t, "slot": s, "param": i})


def probe(t, s, i, settle):
    before = read(t, s, i)
    v0 = before["v"]
    target = v0 - 0.25 if v0 > 0.5 else v0 + 0.25
    results = {}
    for m in METHODS:
        r = call("plugin_write_probe", {"track": t, "slot": s, "param": i, "value": target, "method": m})
        if not r.get("ok"):
            results[m] = "err: " + r.get("error", "?")
            continue
        time.sleep(settle)
        after = read(t, s, i)
        moved = abs(after["v"] - v0) > 0.01 or after["s"] != before["s"]
        results[m] = f"OK {before['s']!r}->{after['s']!r}" if moved else "ignored"
        if moved:
            call("plugin_write_probe", {"track": t, "slot": s, "param": i, "value": v0, "method": m})
            time.sleep(settle)
    return before["name"], results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", default="0-6")
    ap.add_argument("--params", type=int, default=3, help="named params to test per plugin")
    ap.add_argument("--target", help="track:slot:param")
    ap.add_argument("--settle", type=float, default=0.4)
    ap.add_argument("--methods", default=",".join(METHODS))
    a = ap.parse_args()
    METHODS[:] = a.methods.split(",")

    if a.target:
        cases = [tuple(int(x) for x in a.target.split(":"))]
    else:
        lo, hi = (int(x) for x in a.tracks.split("-"))
        cases = []
        for t in range(lo, hi + 1):
            for sl in call("plugin_list", {"track": t})["slots"]:
                params = call("plugin_get_params", {"track": t, "slot": sl["slot"]})["params"]
                cases += [(t, sl["slot"], p["i"]) for p in params[: a.params]]

    plugin_names = {}
    for t, s, i in cases:
        if (t, s) not in plugin_names:
            plugin_names[(t, s)] = next(
                (x["name"] for x in call("plugin_list", {"track": t})["slots"] if x["slot"] == s), "?")
        name, res = probe(t, s, i, a.settle)
        print(f"ins {t} slot {s} {plugin_names[(t, s)]} / p{i} {name}")
        for m in METHODS:
            print(f"    {m:<10} {res[m]}")


if __name__ == "__main__":
    main()
