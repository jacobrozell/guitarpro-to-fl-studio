#!/usr/bin/env python3
"""Set an FL plugin parameter to a target *display* value (e.g. 250 Hz, -3 dB).

FL params are normalised 0..1 with plugin-specific curves, so this bisects on
the value until FL's own readback string matches the target. Assumes the
display value rises with the normalised value (true for freq/level/width).

Usage:
  python scripts/fl_param.py TRACK SLOT PARAM TARGET     # PARAM = index or exact name
  python scripts/fl_param.py 3 0 "Band 2 freq" 250
"""

from __future__ import annotations

import re
import sys
import time

from push_to_fl import call


def resolve(track: int, slot: int, param: str) -> int:
    if param.isdigit():
        return int(param)
    start = 0
    while start is not None:
        r = call("plugin_get_params", {"track": track, "slot": slot, "start": start})
        for p in r["params"]:
            if p["name"] == param:
                return p["i"]
        start = r.get("next_start")
    raise SystemExit(f"no param named {param!r}")


def shown(r: dict) -> float:
    s = r["s"].replace(",", "")
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", s)]
    if not nums:
        raise SystemExit(f"can't parse readback {s!r}")
    v = max(nums) if ":" in s else nums[0]  # ratios read "1:4.0" or "4.0:1"
    return v * 1000 if "khz" in s.lower() else v


def write(track: int, slot: int, idx: int, value: float, settle: float = 0.08) -> dict:
    """Write, then read back in a separate call (same-call readbacks can be stale)."""
    call("plugin_set_param", {"track": track, "slot": slot, "param": idx, "value": value})
    time.sleep(settle)
    return call("plugin_get_param", {"track": track, "slot": slot, "param": idx})


def set_choice(track: int, slot: int, idx: int, label: str) -> dict:
    """Set a stepped param (e.g. EQ band type) by its display string."""
    for i in range(51):
        r = write(track, slot, idx, i / 50)
        if r["s"].strip().lower() == label.lower():
            return r
    raise SystemExit(f"no value of param {idx} shows {label!r}")


def set_display(track: int, slot: int, idx: int, target: float, steps: int = 18) -> dict:
    lo, hi, best = 0.0, 1.0, None
    for _ in range(steps):
        mid = (lo + hi) / 2
        r = write(track, slot, idx, mid)
        cur = shown(r)
        if best is None or abs(cur - target) < abs(shown(best) - target):
            best = r
        if cur < target:
            lo = mid
        else:
            hi = mid
    return write(track, slot, idx, best["v"])


if __name__ == "__main__":
    track, slot, param, target = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], float(sys.argv[4])
    print(set_display(track, slot, resolve(track, slot, param), target))
