# Agent prompt: Guitar Pro MIDI → mixed FL project → MP3

Prerequisites: daemon running, FL open on `templates/gp-super.flp`, MCP Apply run once this session. Python deps from `requirements.txt` installed.

```
Guitar Pro MIDI: <PATH_TO.mid>

1. python scripts/prepare_gp_midi.py "<PATH_TO.mid>" --out songs/<slug>
   Show report.md. Flag any unassigned, dropped, or overflow tracks.
2. python scripts/push_to_fl.py songs/<slug>/notes.json
   If auto-trigger does not apply notes, the user runs each MCP <ch> <track>
   script from that channel's piano roll (Tools → Scripting).
3. Unused template channels are already muted. If a guitar overflowed onto a
   clean slot, unmute Fast Dist and Blood Overdrive on that insert.
4. Per-song fader and pan tweaks only. Mix defaults are in the template.
5. User saves and quits FL. Then scripts/render_mp3.sh and scripts/measure_mp3.py.
```

Do not invent plugin loads. Only control plugins already on the mixer or channels.
