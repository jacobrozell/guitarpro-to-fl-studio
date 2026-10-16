#!/usr/bin/env python3
"""Write prepare_gp_midi.py output into the open FL super template via the MCP daemon.

Talks to the daemon over TCP (127.0.0.1:9787) so thousands of notes never pass
through MCP tool arguments. Sets the tempo, mutes template slots the song
doesn't use, names used mixer inserts (slot + 1) after the GP tracks, then per
track selects its slot channel and applies notes into the current pattern.

Prereqs: template open, pattern 1 selected, MCP_Apply run once this FL session.

Usage:
  python scripts/push_to_fl.py songs/<slug>/notes.json [--only drums,bass] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path

ADDR = ("127.0.0.1", 9787)


def rpc(req: dict, timeout: float = 30.0) -> dict:
    with socket.create_connection(ADDR, timeout=timeout) as s:
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf)


def call(cmd: str, params: dict | None = None) -> dict:
    resp = rpc({"op": "call", "cmd": cmd, "params": params, "timeout": 10})
    if not resp.get("ok"):
        raise SystemExit(f"{cmd} failed: {resp.get('error')}")
    return resp["data"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("notes_json", type=Path)
    ap.add_argument("--only", help="comma-separated roles to push")
    ap.add_argument("--tempo", type=float, help="override tempo_bpm from notes.json")
    ap.add_argument("--settle", type=float, default=2.0, help="seconds to let FL apply each track")
    ap.add_argument("--compact", action="store_true",
                    help="map only the used slots onto channels 0..N-1 (quick tests without the full super template)")
    ap.add_argument("--scripts-only", action="store_true",
                    help="only write per-track 'MCP <ch> <track>' piano-roll scripts; run each by hand")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(args.notes_json.read_text())
    if args.compact:
        order = sorted({t["fl_channel"] for t in data["tracks"] if t["fl_channel"] is not None})
        for t in data["tracks"]:
            if t["fl_channel"] is not None:
                t["fl_channel"] = order.index(t["fl_channel"])
        data["slot_count"] = len(order)
    only = set(args.only.split(",")) if args.only else None
    skipped = [t["name"] for t in data["tracks"] if t["fl_channel"] is None]
    if skipped:
        print(f"no free slot (skipped): {', '.join(skipped)}")
    tracks = [t for t in data["tracks"] if t["fl_channel"] is not None and (not only or t["role"] in only)]

    health = rpc({"op": "health"})
    if not health.get("alive"):
        raise SystemExit(f"FL bridge not alive: {health}")
    channel_count = call("get_project_state")["channel_count"]
    if channel_count < data["slot_count"]:
        raise SystemExit(f"Open the super template: project has {channel_count} channels, "
                         f"expected {data['slot_count']}.")

    tempo = args.tempo or data["tempo_bpm"]
    used = {t["fl_channel"] for t in data["tracks"] if t["fl_channel"] is not None}
    print(f"tempo -> {tempo}; muting unused slots {sorted(set(range(data['slot_count'])) - used)}"
          + (" (dry run)" if args.dry_run else ""))
    if not args.dry_run:
        call("set_tempo", {"bpm": tempo})
        for ch in range(channel_count):
            call("channel_set_mute", {"channel": ch, "state": ch not in used})
        for t in data["tracks"]:
            if t["fl_channel"] is not None:
                call("mixer_set_name", {"track": t["fl_channel"] + 1, "name": t["name"]})

    for t in tracks:
        print(f"ch {t['fl_channel']} [{t['slot']}] <- {t['name']} ({t['role']}, {len(t['notes'])} notes)")
        if args.dry_run:
            continue
        slug = args.notes_json.parent.name
        script = f"MCP {slug} {t['slot'] or t['name']}"
        res = rpc({"op": "apply_notes", "notes": t["notes"], "mode": "replace",
                   "trigger": False, "script_name": script}, timeout=60)
        if not res.get("ok"):
            raise SystemExit(f"writing {script} failed: {res}")
        if args.scripts_only:
            continue
        call("channel_select", {"channel": t["fl_channel"]})
        time.sleep(0.3)
        res = rpc({"op": "apply_notes", "notes": t["notes"], "mode": "replace"}, timeout=60)
        if not res.get("ok") or not res.get("triggered"):
            raise SystemExit(f"apply failed on {t['name']}: {res}")
        time.sleep(args.settle)
    print("done — check each channel's piano roll, then save (Cmd+S).\n"
          "If a channel is wrong/empty: open its piano roll → Tools → Scripting → "
          "'MCP <ch> <track>' for that channel.")


if __name__ == "__main__":
    main()
