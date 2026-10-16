#!/usr/bin/env python3
"""Write a second 'take' of one track as a named piano-roll script.

Each note (and its slides, which share its color) moves by a seeded random
timing offset and gets a small velocity change, so a hard-panned double
sounds like two players instead of one copy.

Usage: make_double.py songs/requiem/notes.json "Distortion Guitar" [--ms 7] [--seed 11]
Then open the cloned channel's piano roll and run Tools > Scripting > "MCP Double <track>".
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from push_to_fl import rpc  # noqa: E402


def double(notes, bpm, ms, rng, beats_per_bar=4):
    bars_per_ms = bpm / 60 / beats_per_bar / 1000
    out, last_shift = [], {}
    for n in sorted(notes, key=lambda n: (n["time_bars"], n.get("slide", False))):
        n = dict(n)
        if n.get("slide"):
            shift = last_shift.get(n.get("color"), 0.0)
        else:
            shift = max(-2.5 * ms, min(2.5 * ms, rng.gauss(0, ms))) * bars_per_ms
            last_shift[n.get("color")] = shift
            n["velocity"] = round(max(0.05, min(1.0, n["velocity"] + rng.gauss(0, 0.03))), 4)
        n["time_bars"] = max(0.0, n["time_bars"] + shift)
        out.append(n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("notes_json", type=Path)
    ap.add_argument("track")
    ap.add_argument("--ms", type=float, default=7.0, help="timing spread (std dev, ms)")
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()

    data = json.loads(a.notes_json.read_text())
    t = next(t for t in data["tracks"] if t["name"] == a.track)
    notes = double(t["notes"], data["tempo_bpm"], a.ms, random.Random(a.seed))
    name = f"MCP Double {a.track}"
    res = rpc({"op": "apply_notes", "notes": notes, "mode": "replace", "trigger": False, "script_name": name},
              timeout=60)
    if not res.get("ok"):
        raise SystemExit(f"writing {name} failed: {res}")
    print(f"wrote '{name}' ({len(notes)} notes, ±{a.ms:g} ms)")


if __name__ == "__main__":
    main()
