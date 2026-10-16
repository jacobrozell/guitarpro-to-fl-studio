# Design: Guitar Pro MIDI → expressive, mixed FL project → MP3

Working design notes for this repo. User-facing steps are in the root README.



**Goal (from the original ask):** an agent takes a Guitar Pro `.mid` and, with one prompt + scripts, produces a **velocity-considered, mixed `.flp` and an `.mp3`**. Manual steps only where FL's API can't reach.

**Test file:** `~/Downloads/full short melodic tapping song.mid` · **Bridge:** working · **FL:** 2026 (v26.1.7)

---

## What research changed

| Old assumption | Reality | Change |
|---|---|---|
| GP MIDI "already has mild dynamics — preserve it" | 99.7% of notes are velocity **76** (GP's default *mf*); drums 100% flat | Velocity is **generated** per role, not preserved → `prepare_gp_midi.py` |
| Bulk notes via FL File → Import | Importer always creates **new FLEX/GM channels** — template instruments go unused | Agent writes notes into template channels via daemon (`push_to_fl.py`) |
| Notes via MCP tool calls | 3.4k notes ≈ 75k tokens of tool args | Script talks to daemon TCP directly; MCP stays for mixing |
| MP3 export is manual | FL has a CLI renderer: `open -a "FL Studio 2026" --args -R -Emp3 "<flp>"` (verified FL 2026; `-F<flp>` silently doesn't render) | `render_mp3.sh` (FL must be closed; ~90 s for a 5 min song) |
| Need third-party sounds | Stock **FLEX** (Distortion/Overdriven Guitar presets; FL Slayer is Windows-only), **BooBass**, **FPC** (GM 36–51) | Template is all stock |
| Per-song template | FL API can't load plugins; `.flp` generation offline is fragile | One **super template** + GM program → slot map |
| Drums map 1:1 | GP uses 35/52/55/57, outside FPC's pads | Remap 35→36, china/splash/crash2→49 (louder hit kept on collisions) |

## Velocity model (what "velocity considered" means here)

Metric accent (downbeat > beat 3 > beats > 8ths > 16ths) plus role rules, then ±3 jitter (seeded, repeatable). Notes GP marked softer stay proportionally softer.

- **Drums:** backbeat snare ~118, ghosted off-beat snares ~72, snare/tom fills crescendo, hats accent on beats, crashes ~112, fast double-kick offbeats trimmed
- **Bass:** downbeat-led, sustained notes slightly firmer
- **Rhythm:** chords > single notes > chugs (~88); down-strum (higher strings lighter)
- **Lead:** phrase start +8, phrase peak +5, phrase tail −5, fast tapped/legato interior −4

Test song result: 1–3 distinct velocities per track → 22–52.

## Known losses (accepted for v1)

- **Tempo map:** FL can't get tempo automation via API, so FL runs one tempo (dominant). With `--tempo-mode auto` (default), songs whose tempo varies > 5% are **baked**: note times are converted to real time at that tempo, so playback/MP3 match Guitar Pro exactly, but notes sit off FL's grid in sections at other tempos. `--tempo-mode fixed` keeps the grid and flattens tempo changes.
- **Pitch bends → slide notes.** Each GP bend becomes a bend slide + release slide. The slide **length = GP's actual rise/fall time** (from the pitch-wheel curve, honoring the track's bend range RPN, ±6 st here), clipped to end before the bent note ends so it always reaches its target. Bent note + its slides share a note color, so other chord notes don't move. Slides only work on **native FL instruments** (the whole super template) — verified by ear, including chord-isolated bends. Tapping song: 6 bends → 12 slides; Requiem: 32 → 64. Vibrato becomes a zigzag of short slides. Not modeled: a bend still held when the next note starts.
- Tapping/palm-mute articulations aren't in GP's MIDI at all.

---

## Pipeline

```
song.mid ──prepare_gp_midi.py──▶ songs/<slug>/{notes.json, expressive.mid, report.md}   [agent]
         ──push_to_fl.py──────▶ mapped slots filled, unused muted, inserts named, tempo   [agent]
         ──MCP────────────────▶ gain stage, Mix Doctor, EQ/comp                          [agent, you approve]
         ──Cmd+S, quit FL─────▶ songs/<slug>/<slug>.flp                                   [you]
         ──render_mp3.sh──────▶ songs/<slug>/<slug>.mp3 → fl_analyze_audio sanity check   [agent]
```

### Phase 0 — Guitar Pro super template (you, once)

Hard caps and load checklist: [`templates/README.md`](templates/README.md). Map: `scripts/gp_instrument_map.json`. After instruments are loaded, `scripts/build_template.py` names, routes, and applies Requiem mix defaults.

| Cap | Limit | Over cap |
|---|---|---|
| Drums | 1 kit → 5 mixer channels (Kick, Snare, Toms, Hats, Cymbals) | extra drum track dropped |
| Bass | 2 | dropped |
| Electric guitar | 4 (dist + clean share the pool) | 5th dropped |
| Acoustic | 1 | dropped |
| Piano | 2 | dropped |
| Pads / synth / fallback | 1 each | dropped |

Channel *N* → mixer insert *N + 1*. Buses: Drum Bus **18**, Gtr Bus **19**, Drum Crush **20**.

Load 17 channels + those 3 bus inserts, Pattern 1 at bar 1, Song mode. Say **"template ready"** — agent runs `build_template.py`. You Save As `templates/gp-super.flp`.

**Template mix defaults (proven on Requiem; values in `scripts/mix_requiem.py` passes 1–3):**

| Where | Chain / settings |
|---|---|
| Drums | EQ2 −3 dB @ 400 Hz, +7 dB high shelf @ 6 kHz · Fruity Limiter comp −12 dB, 4:1, 10/120 ms · Reeverb 2 room: 250 Hz–7 kHz, 5 ms, size 25, 0.7 s, ER 70%, wet 12% |
| Bass | FLEX bass → EQ2 low shelf −4 dB @ 110 Hz, −3 dB @ 250 Hz, +boost ~900 Hz · Blood Overdrive (~43% pre amp, Post Gain ≤ noon, ~60% mix) · Limiter comp −10 dB, 3:1, 10/150 ms |
| Guitars (each) | EQ2 HP 100 Hz, −3 dB @ 300 Hz, +6 dB @ 3 kHz, +3 dB shelf @ 8 kHz · Blood Overdrive / Fast Dist (not Distructor) · no insert reverb (the bus room covers it) · pans ±0.35 |
| Gtr Bus | Spreader 70%, low-freq bypass 200 Hz · Reeverb 2 room: 200 Hz–6 kHz, 10 ms predelay, size 25, 0.8 s, wet 15% |
| Drum Crush (ins 6) | Drums send here · Fruity Limiter comp −30 dB, 10:1, 1/60 ms, gain +10 dB · fader ≈ −12 dB to taste |
| Master | Parametric EQ 2 first: HP 30 Hz, −1.5 dB @ 300 Hz, +1.5 dB @ 3.5 kHz, +2 dB shelf @ 10 kHz → Maximus master pre gain +17 dB, post gain −1 dB. No Emphasizer |

Result: peak −0.9 dBFS, RMS −13 dBFS, mid-forward balance. Plugin params are all settable over MCP (fork fix), so the agent can re-apply these per song.

Tapping-song mapping: Drumkit split → Kick/Snare/Hats/Cymbals, Bass → Bass 1, Rhythm → Gtr 1 Dist, Lead → Gtr 3 Clean, Additional Leads → Gtr 4 Clean.

### Phase 1 — Prepare (agent) ✅ done for test song

```bash
runtime/venv/bin/python scripts/prepare_gp_midi.py "<song>.mid"
```

### Phase 2 — Push notes (agent)

Prereq: Piano roll → Tools → Scripting → **MCP Apply** once per FL session.

```bash
runtime/venv/bin/python scripts/push_to_fl.py songs/<slug>/notes.json
```

Verify each channel's piano roll and that the Pattern 1 clip spans the whole song (~75 bars); drag the clip end if not.

### Phase 3 — Mix (agent proposes, you approve)

`fl_gain_stage` → play + `fl_diagnose_mix` → one fix at a time via `fl_apply_mix_fix` / EQ / compression intents.

**FL 2026 API reality (Requiem test):** faders, pans, routing/buses, renames work. Plugin param writes need an explicit `pickupMode` (`midi.PIM_None`) or FL silently drops them — fixed in the fork ([jacobrozell/flstudio-mcp](https://github.com/jacobrozell/flstudio-mcp), branch `jacob/fl2026`); `scripts/probe_plugin_writes.py` re-checks this. Some on/off switches (e.g. Multiband Compressor limiter) still don't move. Also: `fl_apply_eq_intent` treats a 0 dB high-pass band as "free" and overwrites it — apply gain moves before high-passes. Peak reads right after a seek can spike (+25 dBFS glitch); sample steadily. Targets: lead over rhythm, kick/bass separated (HPF guitars), master peaks ≤ −3 dBFS.

### Phase 4 — Save + render

You: **Save As** `songs/<slug>/<slug>.flp`, quit FL. Agent: `scripts/render_mp3.sh songs/<slug>/<slug>.flp`, then `fl_analyze_audio` on the MP3. If the CLI render fails on FL 2026, fall back to File → Export → MP3.

---

## Success criteria (test song)

- [x] Expressive velocities generated (no flat tracks), drums mapped to FPC
- [ ] All 5 parts audible end-to-end (~2:48 at 107 BPM)
- [ ] Mix: lead cuts, bass solid, no master clipping
- [ ] `.flp` + `.mp3` in `songs/full-short-melodic-tapping-song/`
- [ ] CLI render verified on FL 2026

## Later

On-grid tempo fidelity (tempo automation clip), a save command in the controller script, per-song kit maps.

### Backlog

- ~~Mute / unmute plugin slots over MCP~~ coded (`plugin_set_slot` → `mixer.setPluginMuteState` / `setPluginMixLevel`). Needs an FL restart to load, then a live probe.
- **Add / remove plugins over MCP.** FL still cannot instantiate plugins. Super-chain template + slot mute is the path (`templates/README.md`).
- Clone channel (still no API).
- ~~Micro-timing humanization~~ done: `prepare_gp_midi.py` (on by default, `--no-timing` turns it off).
  - kick ±2 ms, snare +4 ms laid back, hats/cymbals ±3 ms
  - bass +3 ms
  - rhythm chords strum low→high (1.5 ms/string)
  - leads ±5 ms

  It uses its own seed, so velocities don't change.
- ~~Parallel drum compression~~ done: `mix_requiem.py --pass 5`. Drums send to insert 6 "Drum Crush" (Fruity Limiter: −30 dB, 10:1, 1/60 ms, +10 dB), whose fader sets the blend.
- ~~Controller cmds: channel → insert, send level~~ coded (`channel_set_target`, `mixer_set_route_level`). Clone channel still missing.
