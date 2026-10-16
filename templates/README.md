# Guitar Pro super template (`gp-super.flp`)

`gp-super.flp` is the built project: 17 stock channels, bus inserts, and the mix defaults from `scripts/build_template.py`. Open it and run a song. The steps at the bottom are only for rebuilding the template from an empty project.

Hard caps are enforced by `scripts/gp_instrument_map.json` + `prepare_gp_midi.py`. Extra parts are **dropped** and listed in `report.md`.

| Family | Cap | What happens over cap |
|---|---|---|
| Drums | **1 kit**, split onto 5 mixer channels | A second drum track is dropped |
| Bass | **2** | 3rd bass dropped |
| Electric guitar | **4** total (dist + clean share the pool) | Dist prefers Gtr 1–2, clean prefers Gtr 3–4, then either takes the next free guitar slot. 5th guitar dropped |
| Acoustic | **1** | Extra dropped |
| Piano / keys | **2** | Extra dropped |
| Pads / strings | **1** | Extra dropped |
| Synth lead | **1** | Extra dropped |
| Anything else | **1 Fallback** | Extra dropped |

Channel *N* → mixer insert *N+1*. Buses are mixer-only (no channel-rack instrument).

## Channel rack (load in this order)

| Ch | Insert | Name | Instrument (stock) |
|---:|---:|---|---|
| 0 | 1 | Kick | FPC, same kit — clone this 5× |
| 1 | 2 | Snare | FPC clone |
| 2 | 3 | Toms | FPC clone |
| 3 | 4 | Hats | FPC clone |
| 4 | 5 | Cymbals | FPC clone |
| 5 | 6 | Bass 1 | FLEX bass |
| 6 | 7 | Bass 2 | FLEX bass |
| 7 | 8 | Gtr 1 Dist | FLEX Distortion Guitar |
| 8 | 9 | Gtr 2 Dist | FLEX Distortion Guitar |
| 9 | 10 | Gtr 3 Clean | FLEX clean / overdriven guitar |
| 10 | 11 | Gtr 4 Clean | FLEX clean / overdriven guitar |
| 11 | 12 | Acoustic | FLEX acoustic |
| 12 | 13 | Piano 1 | FL Keys |
| 13 | 14 | Piano 2 | FL Keys |
| 14 | 15 | Pads | FLEX pads/strings |
| 15 | 16 | Synth | 3x Osc or Sytrus |
| 16 | 17 | Fallback | FLEX |

Add mixer inserts if the mixer stops at Insert 18. You need inserts **18–20** named by the build script.

| Insert | Name | Plugins |
|---:|---|---|
| 18 | Drum Bus | Parametric EQ 2, Fruity Limiter, Reeverb 2 |
| 19 | Gtr Bus | Spreader, Reeverb 2 |
| 20 | Drum Crush | Fruity Limiter |
| 0 Master | Master | Parametric EQ 2 **then** Maximus |

## Per-insert plugin chains (preload; mute unused)

FL cannot add plugins over MCP. Load these once. `build_template.py` will mute the ones a song doesn't need.

**Kick / Snare / Toms / Hats / Cymbals:** Parametric EQ 2

**Bass 1–2:** Parametric EQ 2, Fruity Limiter, Fruity Blood Overdrive

**Gtr 1–2 Dist:** Parametric EQ 2, Fruity Fast Dist, Fruity Blood Overdrive

**Gtr 3–4 Clean:** Parametric EQ 2, Fruity Fast Dist *(starts muted)*, Fruity Blood Overdrive *(starts muted)* — unmute when a dist guitar overflows onto a clean slot

**Acoustic / Piano 1–2:** Parametric EQ 2, Reeverb 2

**Pads / Synth / Fallback:** Parametric EQ 2

## Your steps

1. File → New. Put **Pattern 1** at bar 1 in the Playlist, **Song** mode.
2. Load the 17 channels and the plugin chains above. Clone FPC for the five drum channels so they share a kit.
3. Restart FL once so it picks up the `jacob/fl2026` controller (slot mute, channel→insert, send level).
4. Say **"template ready"**. The agent runs `scripts/build_template.py` (names, routing, Requiem mix defaults).
5. **Save As** `templates/gp-super.flp`.

## First song on the template

`full-short-melodic-tapping-song` (already re-prepared against this map):

| GP track | Slot |
|---|---|
| Drumkit | Kick / Snare / Toms / Hats / Cymbals (whichever pieces have notes) |
| Electric Bass | Bass 1 |
| Rhythm Guitar (GM 30) | Gtr 1 Dist |
| Lead Guitar (GM 27) | Gtr 3 Clean |
| Additional Leads (GM 27) | Gtr 4 Clean |
