#!/usr/bin/env python3
"""Write prepare_gp_midi.py notes into a copy of the super template.

FL stays closed. The template's pattern notes are one length-prefixed event
(id 224, 24 bytes each). This replaces that event, sets the project tempo,
and stretches the single playlist clip of pattern 1 out to the last note.

FL 2026 writes event 172 as 3 bytes. A parser that treats it as a dword
loses alignment and must not be used to resave the file.

Usage:
  python scripts/splice_flp.py songs/<slug>/notes.json \\
      --template templates/gp-super.flp --out songs/<slug>/<slug>.flp
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
from pathlib import Path

PPQ = 96
BAR = PPQ * 4
NOTE_FLAGS = 0x4000
SLIDE_FLAG = 0x0008
PATTERN_BASE = 20480
PATTERN_CLIP = struct.pack("<HH", PATTERN_BASE, PATTERN_BASE + 1)  # pattern 1
TEMPO_ID = 156
NOTES_ID = 224
SHORT_DWORD = {172}


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    n = s = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << s
        if b < 0x80:
            return n, i
        s += 7
        if s > 35:
            raise ValueError("bad varint")


def _encode_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def parse_events(data: bytes) -> tuple[bytes, list[tuple[int, bytes, bytes]], int]:
    """Return (header through FLdt size field, events, data-start).

    Each event is (type, payload, raw bytes).
    """
    if data[:4] != b"FLhd" or data[14:18] != b"FLdt":
        raise SystemExit("not an FLP")
    data_start = 22
    data_size = int.from_bytes(data[18:22], "little")
    end = data_start + data_size
    if end != len(data):
        raise SystemExit(f"FLdt size {data_size} does not match file length {len(data) - data_start}")

    events: list[tuple[int, bytes, bytes]] = []
    i = data_start
    while i < end:
        start = i
        typ = data[i]
        i += 1
        if typ in SHORT_DWORD:
            ln = 3
        elif typ < 64:
            ln = 1
        elif typ < 128:
            ln = 2
        elif typ < 192:
            ln = 4
        else:
            ln, i = _varint(data, i)
        payload = data[i : i + ln]
        i += ln
        if i > end:
            raise SystemExit(f"event {typ} overruns the file at {start}")
        events.append((typ, payload, data[start:i]))
    return data[:data_start], events, data_start


def encode_event(typ: int, payload: bytes) -> bytes:
    if typ in SHORT_DWORD:
        if len(payload) != 3:
            raise SystemExit(f"event {typ} must be 3 bytes")
        return bytes([typ]) + payload
    if typ < 64:
        ln = 1
    elif typ < 128:
        ln = 2
    elif typ < 192:
        ln = 4
    else:
        return bytes([typ]) + _encode_varint(len(payload)) + payload
    if len(payload) != ln:
        raise SystemExit(f"event {typ} payload is {len(payload)} bytes, expected {ln}")
    return bytes([typ]) + payload


def build_notes(tracks: list[dict]) -> bytes:
    recs = bytearray()
    for track in tracks:
        ch = track.get("fl_channel")
        if ch is None:
            continue
        for note in track["notes"]:
            pos = max(0, int(round(note["time_bars"] * BAR)))
            length = max(1, int(round(note["length_bars"] * BAR)))
            flags = NOTE_FLAGS | (SLIDE_FLAG if note.get("slide") else 0)
            fine = max(0, min(240, 120 + int(note.get("pitchofs") or 0)))
            vel = max(0, min(128, int(round(float(note["velocity"]) * 128))))
            recs += struct.pack(
                "<IHHIHHBBBBBBBB",
                pos,
                flags,
                ch,
                length,
                int(note["pitch"]),
                0,
                fine,
                0,
                64,
                int(note.get("color") or 0) & 0x0F,
                64,
                vel,
                128,
                128,
            )
    if len(recs) % 24:
        raise SystemExit("note records are not 24 bytes")
    return bytes(recs)


def stretch_clip(payload: bytes, new_length: int) -> bytes:
    """Grow the pattern-1 clip. Its length is stored twice, 20 bytes apart."""
    buf = bytearray(payload)
    at = buf.find(PATTERN_CLIP)
    if at < 4:
        raise SystemExit("playlist clip for pattern 1 not found")
    old = int.from_bytes(buf[at + 4 : at + 8], "little")
    struct.pack_into("<I", buf, at + 4, new_length)
    twin = at + 4 + 20
    if twin + 4 <= len(buf) and int.from_bytes(buf[twin : twin + 4], "little") == old:
        struct.pack_into("<I", buf, twin, new_length)
    return bytes(buf)


def splice(template: bytes, notes_doc: dict) -> bytes:
    header, events, _ = parse_events(template)
    notes = build_notes(notes_doc["tracks"])
    if not notes:
        raise SystemExit("no notes to write")
    max_end = 0
    for off in range(0, len(notes), 24):
        pos, length = struct.unpack_from("<I4xI", notes, off)
        max_end = max(max_end, pos + length)
    clip_length = ((max_end + BAR - 1) // BAR) * BAR
    tempo = int(round(float(notes_doc["tempo_bpm"]) * 1000))

    saw_notes = saw_tempo = saw_clip = False
    out = bytearray(header)
    for typ, payload, raw in events:
        if typ == NOTES_ID:
            raw = encode_event(typ, notes)
            saw_notes = True
        elif typ == TEMPO_ID:
            raw = encode_event(typ, struct.pack("<I", tempo))
            saw_tempo = True
        elif PATTERN_CLIP in payload:
            raw = encode_event(typ, stretch_clip(payload, clip_length))
            saw_clip = True
        out += raw
    if not (saw_notes and saw_tempo and saw_clip):
        raise SystemExit(f"missing events notes={saw_notes} tempo={saw_tempo} clip={saw_clip}")
    struct.pack_into("<I", out, 18, len(out) - 22)
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("notes_json", type=Path)
    ap.add_argument("--template", type=Path, default=Path(__file__).resolve().parent.parent / "templates" / "gp-super.flp")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    template = args.template.read_bytes()
    header, events, _ = parse_events(template)
    roundtrip = bytearray(header)
    for typ, _payload, raw in events:
        roundtrip += raw
    if bytes(roundtrip) != template:
        raise SystemExit("refusing to edit: event walk does not round-trip this FLP")

    doc = json.loads(args.notes_json.read_text())
    baked = splice(template, doc)
    parse_events(baked)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.resolve() == args.template.resolve():
        raise SystemExit("refusing to overwrite the template")
    args.out.write_bytes(baked)

    notes = build_notes(doc["tracks"])
    max_end = max(
        struct.unpack_from("<I4xI", notes, off)[0] + struct.unpack_from("<I4xI", notes, off)[1]
        for off in range(0, len(notes), 24)
    )
    print(
        f"wrote {args.out}  {len(notes) // 24} notes  "
        f"tempo {doc['tempo_bpm']}  clip {((max_end + BAR - 1) // BAR)} bars  "
        f"({len(baked)} bytes)"
    )


if __name__ == "__main__":
    main()
