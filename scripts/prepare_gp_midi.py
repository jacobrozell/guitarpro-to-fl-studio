#!/usr/bin/env python3
"""Guitar Pro MIDI -> expressive, FL-ready note data.

Guitar Pro exports nearly every note at the same velocity (its "mf"), so this
script *generates* performance dynamics per role (drums / bass / rhythm / lead)
from metric position, chords, runs and phrases, while keeping any dynamics the
author wrote in GP (notes off the track's default velocity stay relatively
softer/louder). Drum notes are remapped onto FPC's default GM pads.

Each track is assigned a super-template slot from its GM program via
gp_instrument_map.json (first free slot in its family, then overflow families,
else unassigned). One drum track is split across Kick/Snare/Toms/Hats/Cymbals.

Usage:
  python scripts/prepare_gp_midi.py song.mid [--out songs/<slug>] [--seed 7]

Writes to the out dir:
  notes.json        per-track notes for push_to_fl.py (velocity 0..1, time in bars of 4 quarters)
  expressive.mid    the same MIDI with new velocities (tempo map, bends intact)
  report.md         velocity before/after, tempo map, bends, drum remaps
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
from collections import Counter
from pathlib import Path

import mido

INSTRUMENT_MAP = Path(__file__).with_name("gp_instrument_map.json")

# FPC default kit covers GM 36..51; fold the rest onto the nearest pad.
FPC_DRUM_MAP = {35: 36, 52: 49, 53: 51, 55: 49, 57: 49, 59: 51}

KICKS = {35, 36}
SNARES = {37, 38, 39, 40}
TOMS = {41, 43, 45, 47, 48, 50}
HATS = {42, 44, 46, 51, 53, 59}
CYMBALS = {49, 52, 55, 57}

METRIC = {"down": 12, "half": 7, "beat": 4, "eighth": 0, "sub": -7}


class Meter:
    def __init__(self, mid: mido.MidiFile):
        self.tpb = mid.ticks_per_beat
        self.sigs: list[tuple[int, int, int]] = []
        self.tempos: list[tuple[int, float]] = []
        for track in mid.tracks:
            tick = 0
            for msg in track:
                tick += msg.time
                if msg.type == "time_signature":
                    self.sigs.append((tick, msg.numerator, msg.denominator))
                elif msg.type == "set_tempo":
                    self.tempos.append((tick, round(mido.tempo2bpm(msg.tempo), 2)))
        self.sigs = sorted(self.sigs) or [(0, 4, 4)]
        self.tempos = sorted(self.tempos) or [(0, 120.0)]
        self.end = max(sum(m.time for m in t) for t in mid.tracks)

    def position(self, tick: int) -> tuple[str, int]:
        """Metric strength + beat index within the bar."""
        start, num, den = self.sigs[0]
        for s in self.sigs:
            if s[0] <= tick:
                start, num, den = s
        beat_len = self.tpb * 4 // den
        pos = (tick - start) % (beat_len * num)
        tol = max(2, self.tpb // 48)

        def on(grid: int) -> bool:
            r = pos % grid
            return r <= tol or grid - r <= tol

        beat = round(pos / beat_len)
        if pos <= tol:
            return "down", 0
        if num == 4 and den == 4 and abs(pos - 2 * beat_len) <= tol:
            return "half", 2
        if on(beat_len):
            return "beat", beat
        if on(self.tpb // 2):
            return "eighth", beat
        return "sub", beat

    def dominant_tempo(self) -> float:
        spans = Counter()
        marks = self.tempos + [(self.end, None)]
        for (t0, bpm), (t1, _) in zip(marks, marks[1:]):
            spans[bpm] += t1 - t0
        return spans.most_common(1)[0][0]

    def spread(self) -> float:
        bpms = [b for _, b in self.tempos]
        return max(bpms) / min(bpms) - 1

    def baked_quarters(self, tick: int, fixed_bpm: float) -> float:
        """Real time of `tick` under the tempo map, as quarters at fixed_bpm."""
        seconds, prev_tick, prev_bpm = 0.0, 0, self.tempos[0][1]
        for t, bpm in self.tempos:
            if t >= tick:
                break
            seconds += (t - prev_tick) / self.tpb * 60 / prev_bpm
            prev_tick, prev_bpm = t, bpm
        seconds += (tick - prev_tick) / self.tpb * 60 / prev_bpm
        return seconds * fixed_bpm / 60


def role_for(name: str, program: int | None, channel: int, seen: set[str]) -> str:
    n = name.lower()
    if channel == 9 or "drum" in n:
        role = "drums"
    elif "bass" in n or (program is not None and 32 <= program <= 39):
        role = "bass"
    elif "lead" in n or "solo" in n:
        role = "lead"
    elif "rhythm" in n or program in (29, 30):
        role = "rhythm"
    else:
        role = "lead"
    if role == "lead" and "lead" in seen:
        role = "lead2"
    seen.add(role)
    return role


DRUM_PIECES = ("kick", "snare", "tom", "hat", "cymbal")


def drum_piece(pitch: int) -> str:
    if pitch in KICKS:
        return "kick"
    if pitch in SNARES:
        return "snare"
    if pitch in TOMS:
        return "tom"
    if pitch in CYMBALS:
        return "cymbal"
    return "hat"  # hats + leftover percussion (tambourine, cowbell, …)


class SlotAllocator:
    def __init__(self, path: Path = INSTRUMENT_MAP):
        cfg = json.loads(path.read_text())
        self.slots = cfg["slots"]
        self.families = cfg["families"]
        self.overflow = cfg.get("overflow", {})
        self.used: dict[int, str] = {}
        self.drums_used = False

    def family(self, program: int | None, channel: int) -> str:
        if channel == 9:
            return "drums"
        for fam, ranges in self.families.items():
            if program is not None and any(lo <= program <= hi for lo, hi in ranges):
                return fam
        return "fallback"

    def assign(self, track_name: str, family: str) -> tuple[int | None, bool]:
        """Return (slot_index, overflow). overflow=True when the slot's family
        is not the requested one (e.g. a 3rd dist guitar on a clean slot)."""
        if family == "drums":
            return None, False  # caller splits onto drum slots
        for want in [family, *self.overflow.get(family, [])]:
            for i, slot in enumerate(self.slots):
                if slot["family"] == want and i not in self.used:
                    self.used[i] = track_name
                    return i, want != family
        return None, False

    def drum_slot(self, piece: str) -> int | None:
        want = {"kick": "Kick", "snare": "Snare", "tom": "Toms", "hat": "Hats", "cymbal": "Cymbals"}[piece]
        for i, slot in enumerate(self.slots):
            if slot["name"] == want:
                return i
        return None


def collect_notes(track: mido.MidiTrack) -> list[dict]:
    active: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    notes, tick = [], 0
    for i, msg in enumerate(track):
        tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            active.setdefault((msg.channel, msg.note), []).append((tick, msg.velocity, i))
        elif msg.type in ("note_off", "note_on"):
            stack = active.get((msg.channel, msg.note))
            if stack:
                start, vel, idx = stack.pop(0)
                notes.append({"pitch": msg.note, "start": start, "length": max(tick - start, 1),
                              "orig": vel, "idx": idx, "off_idx": i, "channel": msg.channel})
    notes.sort(key=lambda n: (n["start"], n["pitch"]))
    return notes


def bend_moves(track: mido.MidiTrack, tpb: int) -> list[tuple[int, int, float]]:
    """Pitch-wheel curve -> [(start_tick, end_tick, target_semitones)].

    A move spans from the last steady value to where the wheel stops moving in
    one direction, so its length is GP's actual bend/release time -- which is
    exactly what an FL slide note's length must be.
    """
    bend_range, rpn, tick, events = 2.0, [None, None], 0, []
    for msg in track:
        tick += msg.time
        if msg.type == "control_change":
            if msg.control in (101, 100):
                rpn[msg.control == 100] = msg.value
            elif msg.control == 6 and rpn == [0, 0]:
                bend_range = float(msg.value)
        elif msg.type == "pitchwheel":
            if events and events[-1][0] == tick:
                events.pop()
            events.append((tick, msg.pitch))

    max_gap = tpb // 4
    moves, i, prev = [], 0, (0, 0)
    while i < len(events):
        t, v = events[i]
        if v == prev[1]:
            prev = (t, v)
            i += 1
            continue
        start = prev[0] if t - prev[0] <= max_gap else t
        direction = v > prev[1]
        end_t, end_v = t, v
        i += 1
        while i < len(events):
            nt, nv = events[i]
            if nt - end_t > max_gap or nv == end_v or (nv > end_v) != direction:
                break
            end_t, end_v = nt, nv
            i += 1
        moves.append((start, end_t, round(end_v / 8192 * bend_range, 1)))
        prev = (end_t, end_v)
    return moves


def bend_slides(notes: list[dict], moves, tpb: int) -> tuple[list[dict], int]:
    """FL slide notes for each bend move, colored with the note they bend.

    Slides retarget the most recently struck sounding note (same color group, so
    the rest of a chord stays put) and are clipped to end before it does --
    a slide cut off by its note's end never reaches the target pitch.
    """
    slides, skipped, color, min_len = [], 0, 0, max(1, tpb // 32)
    for start, end, semis in moves:
        sounding = [n for n in notes if n["start"] <= start + min_len and n["start"] + n["length"] > start]
        if not sounding:
            skipped += 1  # e.g. wheel reset after the note already ended
            continue
        base = max(sounding, key=lambda n: (n["start"], n["pitch"]))
        if "color" not in base:
            color = color % 15 + 1
            base["color"] = color
        s = max(start, base["start"])
        base_end = base["start"] + base["length"]
        length = min(max(end - s, min_len), base_end - s - 1)
        if length < 1:
            skipped += 1
            continue
        whole = int(semis)
        slides.append({"pitch": base["pitch"] + whole, "start": s, "length": length,
                       "vel": base["vel"], "slide": True, "color": base["color"],
                       "pitchofs": round((semis - whole) * 10), "shift_ms": base.get("shift_ms", 0.0)})
    return slides, skipped


def runs(notes: list[dict], max_gap: int) -> list[list[dict]]:
    """Group consecutive notes whose onsets are <= max_gap apart."""
    groups: list[list[dict]] = []
    for n in notes:
        if groups and n["start"] - groups[-1][-1]["start"] <= max_gap:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def shape_drums(notes, meter, out):
    tpb = meter.tpb
    hits = [n for n in notes if n["pitch"] in SNARES | TOMS]
    for run in runs(hits, tpb // 4):
        if len(run) >= 3:  # fill: crescendo into the next downbeat
            for i, n in enumerate(run):
                out[id(n)] = 92 + 24 * i / (len(run) - 1)
    for n in notes:
        if id(n) in out:
            continue
        strength, beat = meter.position(n["start"])
        p = n["pitch"]
        if p in KICKS:
            v = 100 + METRIC[strength] * 0.8
        elif p in SNARES:
            v = 118 if strength in ("beat", "half") and beat % 2 == 1 else 108 if strength != "sub" else 72
        elif p in CYMBALS:
            v = 112
        elif p in HATS:
            v = 84 + {"down": 10, "half": 6, "beat": 6, "eighth": 0, "sub": -10}[strength]
        else:
            v = 100 + METRIC[strength] * 0.5
        out[id(n)] = v
    kicks = [n for n in notes if n["pitch"] in KICKS]
    for a, b in zip(kicks, kicks[1:]):
        if b["start"] - a["start"] < tpb // 4 and meter.position(b["start"])[0] == "sub":
            out[id(b)] -= 6


def shape_bass(notes, meter, out):
    for n in notes:
        v = 94 + METRIC[meter.position(n["start"])[0]] * 0.7
        out[id(n)] = v + (3 if n["length"] >= meter.tpb else 0)


def shape_rhythm(notes, meter, out):
    tpb = meter.tpb
    for chord in runs(notes, 5):
        strength = meter.position(chord[0]["start"])[0]
        length = max(n["length"] for n in chord)
        if len(chord) >= 2:
            base = 108 if length >= 2 * tpb else 100
        elif length <= tpb // 4:
            base = 88  # chug
        else:
            base = 96
        for i, n in enumerate(sorted(chord, key=lambda n: n["pitch"])):
            out[id(n)] = base + METRIC[strength] - 3 * i  # down-strum: top strings lighter


def shape_lead(notes, meter, out, base):
    tpb = meter.tpb
    phrases: list[list[dict]] = []
    for n in notes:
        if phrases:
            prev = phrases[-1][-1]
            if n["start"] - (prev["start"] + prev["length"]) <= tpb // 2:
                phrases[-1].append(n)
                continue
        phrases.append([n])
    for phrase in phrases:
        peak = max(n["pitch"] for n in phrase)
        for i, n in enumerate(phrase):
            strength = meter.position(n["start"])[0]
            v = base + METRIC[strength] * 0.6
            if i == 0:
                v += 8
            if n["pitch"] == peak:
                v += 5
            if len(phrase) > 2 and i == len(phrase) - 1:
                v -= 5
            if n["length"] <= tpb // 3 and strength in ("eighth", "sub"):
                v -= 4  # legato/tapped run interior
            out[id(n)] = v


def humanize(notes, role, meter, rng):
    out: dict[int, float] = {}
    if role == "drums":
        shape_drums(notes, meter, out)
    elif role == "bass":
        shape_bass(notes, meter, out)
    elif role == "rhythm":
        shape_rhythm(notes, meter, out)
    else:
        shape_lead(notes, meter, out, 94 if role == "lead" else 90)

    default = Counter(n["orig"] for n in notes).most_common(1)[0][0]
    floor = 40 if role == "drums" else 30
    for n in notes:
        v = out[id(n)] * (n["orig"] / default) + rng.gauss(0, 3)
        n["vel"] = int(max(floor, min(127, round(v))))


def micro_time(notes, role, rng):
    """Seeded per-note timing offsets (ms) so parts don't sit dead on the grid.

    Drums: snare laid back, kick tight. Bass a touch late. Rhythm chords move
    as one strum (low string first). Leads loosest.
    """
    def jitter(mean, sd):
        return mean + max(-2.5 * sd, min(2.5 * sd, rng.gauss(0, sd)))

    if role == "drums":
        for n in notes:
            p = n["pitch"]
            n["shift_ms"] = (jitter(0, 2) if p in KICKS else jitter(4, 2) if p in SNARES
                             else jitter(2, 3) if p in TOMS else jitter(0, 3))
    elif role == "bass":
        for n in notes:
            n["shift_ms"] = jitter(3, 4)
    elif role == "rhythm":
        for chord in runs(notes, 5):
            base = jitter(0, 4)
            for i, n in enumerate(sorted(chord, key=lambda n: n["pitch"])):
                n["shift_ms"] = base + 1.5 * i
    else:
        for n in notes:
            n["shift_ms"] = jitter(0, 5)


def slugify(path: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")


def stats(vals: list[int]) -> str:
    return f"{min(vals)}–{max(vals)} (avg {statistics.mean(vals):.0f}, {len(set(vals))} distinct)"


def note_payload(notes, slides, bars, bars_per_ms):
    return [{"pitch": n["pitch"],
             "time_bars": round(max(0.0, bars(n["start"]) + n.get("shift_ms", 0.0) * bars_per_ms), 6),
             "length_bars": round(bars(n["start"] + n["length"]) - bars(n["start"]), 6),
             "velocity": round(n["vel"] / 127, 4),
             **{k: n[k] for k in ("slide", "color", "pitchofs") if n.get(k)}}
            for n in notes + slides]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("midi", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-drum-map", action="store_true")
    ap.add_argument("--no-timing", action="store_true", help="keep notes exactly on Guitar Pro's grid")
    ap.add_argument("--tempo-mode", choices=("auto", "fixed", "bake"), default="auto",
                    help="fixed: keep grid, one tempo; bake: keep real timing at one tempo "
                         "(off-grid where tempo differs); auto: bake if tempo spread > 5%%")
    args = ap.parse_args()

    mid = mido.MidiFile(args.midi)
    meter = Meter(mid)
    tempo = meter.dominant_tempo()
    bake = args.tempo_mode == "bake" or (args.tempo_mode == "auto" and meter.spread() > 0.05)
    out_dir = args.out or Path(__file__).resolve().parent.parent / "songs" / slugify(args.midi)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    timing_rng = random.Random(args.seed + 1)  # separate stream: toggling timing never changes velocities

    seen: set[str] = set()
    slots = SlotAllocator()
    tracks_json, report_rows, remaps, bends, dropped = [], [], Counter(), {}, []
    for t_idx, track in enumerate(mid.tracks):
        notes = collect_notes(track)
        if not notes:
            continue
        name = next((m.name for m in track if m.type == "track_name"), f"Track {t_idx}")
        program = next((m.program for m in track if m.type == "program_change"), None)
        role = role_for(name, program, notes[0]["channel"], seen)
        family = slots.family(program, notes[0]["channel"])
        humanize(notes, role, meter, rng)
        if not args.no_timing:
            micro_time(notes, role, timing_rng)

        slides = []
        if role != "drums":
            moves = bend_moves(track, meter.tpb)
            slides, skipped = bend_slides(notes, moves, meter.tpb)
            if moves:
                bends[name] = (len(slides), skipped)

        for n in notes:
            track[n["idx"]] = track[n["idx"]].copy(velocity=n["vel"])
        if role == "drums" and not args.no_drum_map:
            taken = {(n["pitch"], n["start"]) for n in notes if n["pitch"] not in FPC_DRUM_MAP}
            for n in sorted(notes, key=lambda n: -n["vel"]):
                if n["pitch"] not in FPC_DRUM_MAP:
                    continue
                target = FPC_DRUM_MAP[n["pitch"]]
                if (target, n["start"]) in taken:  # pad already hit here: keep the louder one
                    n["drop"] = True
                    continue
                taken.add((target, n["start"]))
                remaps[(n["pitch"], target)] += 1
                for i in (n["idx"], n["off_idx"]):
                    track[i] = track[i].copy(note=target)
                n["pitch"] = target
            notes = [n for n in notes if not n.get("drop")]

        def bars(tick: int) -> float:
            if bake:
                return meter.baked_quarters(tick, tempo) / 4
            return tick / (4 * meter.tpb)

        bars_per_ms = tempo / 60 / 4 / 1000

        if family == "drums":
            if slots.drums_used:
                dropped.append(f"{name} (extra drum kit — cap 1)")
                report_rows.append(f"| {name} | {program} | **dropped (drum cap 1)** | {role} | {len(notes)} | "
                                   f"{stats([n['orig'] for n in notes])} | {stats([n['vel'] for n in notes])} |")
                continue
            slots.drums_used = True
            by_piece: dict[str, list] = {p: [] for p in DRUM_PIECES}
            for n in notes:
                by_piece[drum_piece(n["pitch"])].append(n)
            for piece, piece_notes in by_piece.items():
                if not piece_notes:
                    continue
                slot = slots.drum_slot(piece)
                slots.used[slot] = f"{name} / {slots.slots[slot]['name']}"
                tracks_json.append({
                    "name": f"{slots.slots[slot]['name']}", "role": "drums", "program": program,
                    "family": "drums", "piece": piece, "source": name,
                    "fl_channel": slot, "slot": slots.slots[slot]["name"],
                    "notes": note_payload(piece_notes, [], bars, bars_per_ms),
                })
            split = ", ".join(
                f"{slots.slots[slots.drum_slot(p)]['name']} ({slots.drum_slot(p)}, {len(by_piece[p])})"
                for p in DRUM_PIECES if by_piece[p])
            report_rows.append(f"| {name} | {program} | split → {split} | {role} | {len(notes)} | "
                               f"{stats([n['orig'] for n in notes])} | {stats([n['vel'] for n in notes])} |")
            continue

        slot, overflow = slots.assign(name, family)
        slot_label = f"{slots.slots[slot]['name']} ({slot})" if slot is not None else "**unassigned — over cap**"
        if overflow:
            slot_label += f" *(overflow from {family})*"
        if slot is None:
            dropped.append(f"{name} ({family})")
            tracks_json.append({
                "name": name, "role": role, "program": program, "family": family,
                "fl_channel": None, "slot": None, "notes": [],
            })
        else:
            entry = {
                "name": name, "role": role, "program": program, "family": family,
                "fl_channel": slot, "slot": slots.slots[slot]["name"],
                "notes": note_payload(notes, slides, bars, bars_per_ms),
            }
            if overflow:
                entry["overflow"] = True
                entry["slot_family"] = slots.slots[slot]["family"]
            tracks_json.append(entry)
        report_rows.append(f"| {name} | {program} | {slot_label} | {role} | {len(notes)} | "
                           f"{stats([n['orig'] for n in notes])} | {stats([n['vel'] for n in notes])} |")

    (out_dir / "notes.json").write_text(json.dumps(
        {"source": str(args.midi), "tempo_bpm": tempo, "tempo_baked": bake, "tempo_map": meter.tempos,
         "time_signatures": meter.sigs, "slot_count": len(slots.slots),
         "tracks": tracks_json}, indent=1))
    mid.save(out_dir / "expressive.mid")

    q = meter.tpb
    lines = [
        f"# {args.midi.name}", "",
        f"Length {mid.length:.1f}s · FL tempo **{tempo} BPM** (dominant) · tempo spread "
        f"{meter.spread():.0%} → **{'baked (real timing, off-grid where tempo differs)' if bake else 'fixed (on grid)'}**"
        f" · micro-timing {'off' if args.no_timing else 'on'} · seed {args.seed}", "",
        "| Track | GM prog | Template slot (ch) | Velocity role | Notes | GP velocity | Expressive velocity |",
        "|---|---:|---|---|---:|---|---|", *report_rows, "",
        "Dropped (over cap): " + (", ".join(dropped) or "none"),
        "", "Tempo map (quarter → BPM): " + ", ".join(f"{t / q:g}→{b:g}" for t, b in meter.tempos),
        "", "Time signatures (quarter → sig): " + ", ".join(f"{t / q:g}→{n}/{d}" for t, n, d in meter.sigs),
        "", "Pitch bends → FL slide notes (needs native FL instruments): "
        + (", ".join(f"{k} {s} slides" + (f" ({x} skipped: no sounding note)" if x else "")
                     for k, (s, x) in bends.items()) or "none"),
        "", "Drum remaps for FPC: " + (", ".join(f"{a}→{b} ×{c}" for (a, b), c in remaps.items()) or "none"),
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWrote {out_dir}")


if __name__ == "__main__":
    main()
