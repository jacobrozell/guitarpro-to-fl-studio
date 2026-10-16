# Guitar Pro MIDI → FL Studio

Turn a Guitar Pro `.mid` export into a velocity-aware FL Studio project and an MP3. A stock-plugin template supplies the instruments FL's API cannot load. Scripts write the notes, and [flstudio-mcp](https://github.com/rosasynthesiz/flstudio-mcp) drives the mixer.

Verified on **FL Studio 2026** (v26.1.7), macOS. Plugin-parameter writes need the [`jacob/fl2026`](https://github.com/jacobrozell/flstudio-mcp) fork of that bridge (explicit `pickupMode`). Upstream silently drops those writes on FL 2026.

## What a song run does

1. `scripts/prepare_gp_midi.py` builds dynamics, maps GM programs onto template slots, turns pitch bends into FL slide notes, and remaps drums onto FPC.
2. `scripts/push_to_fl.py` writes those notes into the open template and mutes unused channels.
3. You save and quit FL. `scripts/render_mp3.sh` renders the MP3. `scripts/measure_mp3.py` prints peak, RMS, and band balance.

Mix defaults (EQ, compression, guitar and drum buses, Maximus) already live in `templates/gp-super.flp`. Per-song work is fader and pan tweaks, not rebuilding the chain.

## Requirements

- FL Studio 2026 on macOS, with the stock plugins in the template (FLEX, FPC, FL Keys, 3x Osc, Parametric EQ 2, Fruity Limiter, Fruity Blood Overdrive, Fruity Fast Dist, Reeverb 2, Spreader, Maximus).
- Python 3.10+.
- The `jacob/fl2026` fork of flstudio-mcp, installed and running as the bridge daemon.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`mido` is required for prepare. `librosa`, `numpy`, and `soundfile` are only for `measure_mp3.py`.

## One-time FL setup

See [SETUP.md](SETUP.md). Short version: install the fork, start `fl-studio-mcp-daemon`, enable `FLStudioMCP RX` / `TX` on the same port in MIDI settings, open `templates/gp-super.flp`, and run **MCP Apply** once from a piano roll this session.

## Per song

```bash
python scripts/prepare_gp_midi.py path/to/song.mid --out songs/<slug>
python scripts/push_to_fl.py songs/<slug>/notes.json
```

Check `songs/<slug>/report.md` for dropped or unassigned tracks. Save the project, quit FL, then:

```bash
scripts/render_mp3.sh "/absolute/path/project.flp"
python scripts/measure_mp3.py "/absolute/path/project.mp3"
```

An agent prompt for the same loop is in [AGENT_PROMPT.md](AGENT_PROMPT.md). Slot caps and how to rebuild the template are in [templates/README.md](templates/README.md). The velocity model and accepted losses are in [docs/design.md](docs/design.md).

## Layout

| Path | What |
|---|---|
| `templates/gp-super.flp` | 17 channels, drum/guitar buses, mix defaults |
| `scripts/prepare_gp_midi.py` | MIDI → `notes.json`, `expressive.mid`, `report.md` |
| `scripts/gp_instrument_map.json` | GM program → template slot |
| `scripts/push_to_fl.py` | Notes into the open template via the daemon |
| `scripts/build_template.py` | Names, routing, and mix defaults on a freshly loaded project |
| `scripts/render_mp3.sh` | Command-line MP3 render (FL must be quit) |
| `scripts/measure_mp3.py` | Peak, RMS, spectrum, stereo width |
| `scripts/fl_param.py` | Set a plugin param to a display value (Hz, dB, %) |
| `scripts/make_double.py` | Optional second take for a hard-panned double |

## Limits

FL cannot load plugins, clone channels, or write tempo automation over the API. Songs whose tempo varies by more than 5% are baked to one tempo so the MP3 matches Guitar Pro; notes in the other sections sit off the grid. Palm-mute and tapping articulations are not in Guitar Pro's MIDI. Note apply still needs **MCP Apply** armed once per FL session, and saving the `.flp` is still manual.

## License

MIT. See [LICENSE](LICENSE). The bridge is a separate MIT project.
