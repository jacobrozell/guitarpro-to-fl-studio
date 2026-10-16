# Setup

Verified on macOS with FL Studio 2026 (v26.1.7).

## 1. Bridge

Clone the FL 2026 fork and install it (controller script, server, note bridge):

```bash
git clone -b jacob/fl2026 git@github.com:jacobrozell/flstudio-mcp.git
cd flstudio-mcp
./scripts/install_macos.sh
fl-studio-mcp-daemon
```

The daemon creates virtual MIDI ports `FLStudioMCP RX` and `FLStudioMCP TX` and listens on `127.0.0.1:9787`. Leave it running.

Upstream [rosasynthesiz/flstudio-mcp](https://github.com/rosasynthesiz/flstudio-mcp) is the project this fork is based on. On FL 2026, plugin parameter writes need the fork.

## 2. FL Studio MIDI settings

Restart FL so it loads the controller script.

1. Options → MIDI Settings.
2. Input: `FLStudioMCP RX` → Enable → Controller type **FLStudioMCP** → Port **42**.
3. Output: `FLStudioMCP TX` → Enable → Port **42**.
4. View → Script output should show `[FLStudioMCP] Ready`.

## 3. Cursor (or another MCP client)

Point the client at the installed `fl-studio-mcp` server. After a reload, `fl_ping` should succeed while FL is open and the daemon is running.

Grant Accessibility to the app that sends the piano-roll hotkey (Cursor, Terminal, or whatever runs the daemon): System Settings → Privacy & Security → Accessibility.

## 4. Open the template

File → Open `templates/gp-super.flp`.

Once per FL session, open any channel's piano roll → Tools → Scripting → **MCP Apply**. That arms "run last script" so `push_to_fl.py` can apply notes.

## 5. This repo's Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Health check (FL open):

```bash
python -c "import sys; sys.path.insert(0,'scripts'); from push_to_fl import rpc; print(rpc({'op':'health'}))"
```

`alive: false` with a growing heartbeat age means FL is closed or frozen.
