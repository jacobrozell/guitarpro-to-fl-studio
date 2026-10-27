# Guitar Pro MIDI → FL Studio

Take a Guitar Pro MIDI export and produce a velocity-aware FL Studio project plus an MP3 that plays like a small band: drums, bass, and guitars, with a mix already on the tracks.

Guitar Pro writes almost every note at one velocity (its default *mf*). FL Studio's scripting API can change notes, faders, and plugin knobs on plugins that are already loaded, and it cannot load a new instrument. This repo covers both gaps. A Python script writes the dynamics. A stock-plugin project, `templates/gp-super.flp`, supplies the instruments. [flstudio-mcp](https://github.com/rosasynthesiz/flstudio-mcp) is the bridge that talks to FL.

Verified on **FL Studio 2026** (v26.1.7), macOS. Plugin-knob writes on that version need the [`jacob/fl2026`](https://github.com/jacobrozell/flstudio-mcp) fork of the bridge.

## How it works

```
song.mid
  prepare_gp_midi.py    dynamics, slot map, bends → slides, drum remap
  push_to_fl.py         notes into the open template
  save_quit.sh          Cmd+S, then Cmd+Q
  render_mp3.sh         FL's command-line renderer → .mp3
```

**Prepare** reads the MIDI offline. Each track is assigned a slot in the template from its General MIDI program (lead/solo in the track name counts as a lead). One drum kit is split across kick, snare, toms, hats, and cymbals, and notes outside FPC's pads are folded onto the nearest pad. Velocities are generated per role: metric accents, a louder snare backbeat, softer ghosts and chugs, phrase shape on leads, plus a small seeded jitter. Notes the author already marked softer stay proportionally softer. Pitch-wheel bends become FL slide notes, timed to the original rise and fall. A little micro-timing (laid-back snare, a strum across a chord) is on by default. The script writes `notes.json`, a MIDI file with the new velocities, and `report.md`.

**The template** is a normal `.flp` you open once per song. It has 17 channels of stock plugins (FPC, FLEX, FL Keys, 3x Osc) routed to their own mixer inserts, plus a drum bus, a guitar bus, a parallel drum compressor, and Maximus on the master. EQ, compression, room reverb, and guitar drive are already set. Extra parts past the caps (one kit, two basses, four electric guitars, and so on) are dropped and listed in the report. See [templates/README.md](templates/README.md).

**Push** sends `notes.json` to the bridge daemon over localhost, selects each template channel, and writes the piano roll. Channels the song does not use are muted. FL will only run that piano-roll script if **MCP Apply** has been run once from a piano roll in the current FL session.

**Save and render.** FL must be quit before it will render from the command line. `save_quit.sh` sends Cmd+S and Cmd+Q to the running FL process and checks that the `.flp` timestamp moved. Cmd+S overwrites the file that is already open. `render_mp3.sh` launches FL with `-R -Emp3`. `measure_mp3.py` prints peak, RMS, spectral balance, and stereo width.

The mix is already in the template. Further fader and pan moves are optional. The velocity rules and the accepted losses are in [docs/design.md](docs/design.md).

## Ways to run it

Cursor is optional. The song path is a few scripts. An agent is only there if you want one to run them and nudge the mix.

### Terminal, no Cursor

Install the bridge and this repo's Python packages ([SETUP.md](SETUP.md)). Leave `fl-studio-mcp-daemon` running, open `templates/gp-super.flp`, and run **MCP Apply** once from any piano roll (Tools → Scripting). That menu item arms FL's "run last script" shortcut. It is an FL script, not a Cursor permission.

```bash
python scripts/prepare_gp_midi.py path/to/song.mid --out songs/<slug>
python scripts/push_to_fl.py songs/<slug>/notes.json
scripts/save_quit.sh "/absolute/path/to/the/open/project.flp"
scripts/render_mp3.sh "/absolute/path/to/the/open/project.flp"
python scripts/measure_mp3.py "/absolute/path/to/the/open/project.mp3"
```

Read `songs/<slug>/report.md` before the push. It lists anything that was dropped or could not be assigned a slot.

`push_to_fl.py` talks to the daemon on `127.0.0.1:9787`. `save_quit.sh` and the piano-roll hotkey send keystrokes, so macOS Accessibility has to include **Terminal** (or iTerm), the app you run the scripts from.

### Terminal, no Accessibility grant

Skip the hotkey and the scripted save.

```bash
python scripts/prepare_gp_midi.py path/to/song.mid --out songs/<slug>
python scripts/push_to_fl.py songs/<slug>/notes.json --scripts-only
```

`--scripts-only` still needs the daemon. It writes one piano-roll script per track and does not press keys. In FL, open each used channel's piano roll → Tools → Scripting → `MCP <song> <slot>`. Then save and quit yourself. Render with `render_mp3.sh` after FL has quit, or use File → Export → MP3. Neither of those needs Accessibility.

### No bridge

`prepare_gp_midi.py` never talks to FL. It writes `expressive.mid` (the same song with the new velocities) plus `report.md`. Import that MIDI into any project, including the template, the way you normally would. You keep the dynamics. You give up the automatic slot mapping, muted unused channels, and bend slides, which live in `notes.json` and only land in FL through the push step.

### Optional: an agent in Cursor

[AGENT_PROMPT.md](AGENT_PROMPT.md) is the same loop, handed to an assistant. Wire the MCP server only if you want that. Accessibility then includes Cursor as well as Terminal, because the agent is the one sending Cmd+S and the piano-roll shortcut. The daemon still has to be running. The agent cannot load new plugins.

## Requirements

- FL Studio 2026 on macOS, and the stock plugins named above
- Python 3.10+ (`mido` to prepare; `librosa` only to measure an MP3)
- The `jacob/fl2026` fork of flstudio-mcp, running as `fl-studio-mcp-daemon`, if you push notes into the template. Preparing `expressive.mid` does not need it.

## Limits

- Songs whose tempo varies by more than about 5% are played at one tempo. Note times are converted so the MP3 still matches Guitar Pro, and those sections sit off FL's grid.
- Palm mute and tapping are not in Guitar Pro's MIDI, so they are not in the FL project.
- The first save onto a brand-new path is still FL's Save As dialog. After that, `save_quit.sh` can overwrite the open file.
- FL still cannot load or clone plugins over the API. New instruments mean editing the template.

## License

MIT. See [LICENSE](LICENSE). The bridge is its own MIT project.
