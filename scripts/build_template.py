#!/usr/bin/env python3
"""Wire the Guitar Pro super template once the instruments and plugins are loaded.

Does not load plugins (FL's API can't). Names channels/inserts, routes drums →
Drum Bus, guitars → Gtr Bus, Drum Bus → Drum Crush send, applies Requiem mix
defaults to whatever plugins it finds by name.

Prereqs: FL open on a project with 17 generator channels (see templates/README.md)
and mixer inserts through 20. Restart FL after the jacob/fl2026 controller update
so plugin_set_slot / channel_set_target / mixer_set_route_level exist.

Usage: runtime/venv/bin/python scripts/build_template.py [--dry-run]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fl_param import set_choice, set_display  # noqa: E402
from push_to_fl import call  # noqa: E402

MAP = json.loads(Path(__file__).with_name("gp_instrument_map.json").read_text())
DRY = "--dry-run" in sys.argv


def find_plugin(track: int, *needles: str) -> int | None:
    for s in call("plugin_list", {"track": track})["slots"]:
        name = s["name"].lower()
        if all(n.lower() in name for n in needles):
            return s["slot"]
    return None


def eq(track: int, *moves):
    slot = find_plugin(track, "parametric eq")
    if slot is None:
        print(f"  skip EQ on insert {track} (not loaded)")
        return
    for param, target in moves:
        r = set_choice(track, slot, param, target) if isinstance(target, str) else set_display(track, slot, param, target)
        print(f"  ins {track} EQ {r['name']:<22} -> {r['s']}")


def limiter_comp(track: int, thresh, ratio, attack, release, gain=None):
    slot = find_plugin(track, "limiter")
    if slot is None:
        print(f"  skip Limiter on insert {track}")
        return
    for param, target in ((8, thresh), (9, ratio), (11, attack), (12, release)):
        r = set_display(track, slot, param, target)
        print(f"  ins {track} Limiter {r['name']:<22} -> {r['s']}")
    if gain is not None:
        r = set_display(track, slot, 0, gain)
        print(f"  ins {track} Limiter {r['name']:<22} -> {r['s']}")


def reverb(track: int, low, high, pre, size, decay, er, wet):
    slot = find_plugin(track, "reeverb")
    if slot is None:
        print(f"  skip Reeverb on insert {track}")
        return
    for param, target in ((0, low), (1, high), (2, pre), (3, size), (5, decay), (11, er), (12, wet)):
        r = set_display(track, slot, param, target)
        print(f"  ins {track} Reverb {r['name']:<22} -> {r['s']}")


def mute_slot(track: int, *needles: str, muted=True):
    slot = find_plugin(track, *needles)
    if slot is None:
        return
    r = call("plugin_set_slot", {"track": track, "slot": slot, "muted": muted})
    print(f"  ins {track} slot {slot} muted={r['muted']}")


def main():
    n_slots = len(MAP["slots"])
    st = call("get_project_state")
    if st["channel_count"] < n_slots:
        raise SystemExit(f"Need {n_slots} channel-rack channels, project has {st['channel_count']}. "
                         "Load the instruments in templates/README.md order first.")
    mixer_n = call("mixer_list_tracks", {"start": 0}).get("total") or 18
    buses = {b["name"]: b["insert"] for b in MAP["buses"]}
    need = max(buses.values())
    print(f"channels {st['channel_count']}, mixer tracks reported {mixer_n}, buses through insert {need}")
    if DRY:
        print("(dry run — names/routes/mix skipped)")
        return

    for i, slot in enumerate(MAP["slots"]):
        ins = i + 1
        call("channel_set_name", {"channel": i, "name": slot["name"]})
        call("channel_set_target", {"channel": i, "track": ins})
        call("mixer_set_name", {"track": ins, "name": slot["name"]})
        print(f"ch {i} -> ins {ins} {slot['name']}")

    for name, ins in buses.items():
        call("mixer_set_name", {"track": ins, "name": name})

    # Default FL routes every insert to Master. Bus the drums and guitars instead.
    drum_bus, gtr_bus, crush = buses["Drum Bus"], buses["Gtr Bus"], buses["Drum Crush"]
    for i, slot in enumerate(MAP["slots"]):
        ins = i + 1
        bus = {"drums": drum_bus, "dist_gtr": gtr_bus, "clean_gtr": gtr_bus}.get(slot["family"])
        if bus is None:
            continue
        call("mixer_set_route", {"src": ins, "dst": bus, "enabled": True})
        call("mixer_set_route", {"src": ins, "dst": 0, "enabled": False})
        print(f"  ins {ins} -> {slot.get('bus')} (not Master)")

    call("mixer_set_route", {"src": drum_bus, "dst": crush, "enabled": True})
    call("mixer_set_volume", {"track": crush, "value": -12, "unit": "db"})

    # Guitar pans: dist L/R hard-ish, clean milder
    call("mixer_set_pan", {"track": 8, "value": -0.45})
    call("mixer_set_pan", {"track": 9, "value": 0.45})
    call("mixer_set_pan", {"track": 10, "value": -0.25})
    call("mixer_set_pan", {"track": 11, "value": 0.25})

    # Per-piece drum HPF so kick stays out of hats, etc.
    eq(1, (21, "High pass"), (7, 30))                          # Kick
    eq(2, (21, "High pass"), (7, 100), (12, 3000), (5, 3), (13, 6000), (6, 4))  # Snare
    eq(3, (21, "High pass"), (7, 80), (9, 400), (2, -3))         # Toms
    eq(4, (21, "High pass"), (7, 300), (13, 8000), (6, 5))       # Hats
    eq(5, (21, "High pass"), (7, 400), (13, 8000), (6, 5))       # Cymbals
    eq(drum_bus, (9, 400), (2, -3), (13, 6000), (6, 4))
    limiter_comp(drum_bus, -12, 4, 10, 120)
    reverb(drum_bus, 250, 7000, 5, 25, 0.7, 70, 12)
    limiter_comp(crush, -30, 10, 1, 60, 10)

    for bass in (6, 7):
        eq(bass, (7, 110), (0, -4), (9, 250), (2, -3), (10, 900), (3, 4))
        limiter_comp(bass, -10, 3, 10, 150)

    for gtr in (8, 9, 10, 11):
        eq(gtr, (21, "High pass"), (7, 100), (9, 300), (2, -3), (12, 3000), (5, 6), (13, 8000), (6, 3))
        reverb(gtr, 200, 6000, 10, 25, 0.8, 50, 0)  # wet 0 — bus room covers it

    for keys in (12, 13, 14):  # Acoustic, Piano 1–2: small room, not the guitar bus
        eq(keys, (21, "High pass"), (7, 80))
        reverb(keys, 150, 8000, 8, 30, 1.0, 40, 12)

    mute_slot(10, "blood")
    mute_slot(11, "blood")
    mute_slot(10, "fast dist")
    mute_slot(11, "fast dist")

    spreader = find_plugin(gtr_bus, "spreader")
    if spreader is not None:
        print(f"  Gtr Bus Spreader spread ->", set_display(gtr_bus, spreader, 0, 70)["s"])
        print(f"  Gtr Bus Spreader LF bypass ->", set_display(gtr_bus, spreader, 2, 200)["s"])
    reverb(gtr_bus, 200, 6000, 10, 25, 0.8, 50, 15)

    eq(0, (21, "High pass"), (7, 30), (9, 300), (2, -1.5), (12, 3500), (5, 1.5), (13, 10000), (6, 2))
    maximus = find_plugin(0, "maximus")
    if maximus is not None:
        print("  Master Maximus pre ->", set_display(0, maximus, 47, 17)["s"])
        print("  Master Maximus post ->", set_display(0, maximus, 48, -1)["s"])

    print("done — Save As templates/gp-super.flp")


if __name__ == "__main__":
    main()
