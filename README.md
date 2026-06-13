# OBS ControlDeck

> Creator-focused control toolkit for OBS Studio.

OBS ControlDeck is an open-source OBS toolkit that adds recording markers, timestamped clip notes, scene timers, panic actions, recording checks, a built-in soundpad, local presets, and creator-focused automation.

This repository starts as a Lua script for OBS Studio so it is easy to install and test. The long-term goal is to evolve it into a full OBS plugin or companion panel.

## Features

### Included in the first version

- **AutoMarker** — add timestamped markers while recording.
- **ClipNotes** — save notes such as `Funny`, `Cut`, `Mistake`, `Highlight`, and custom comments.
- **Scene Timer** — track how long each scene was active during a session.
- **Panic Button** — mute a selected mic, hide a selected camera source, switch to a safe scene, and stop active soundpad sources.
- **Recording Guard** — warn when important sources are missing, muted, or misconfigured.
- **AutoIntro** — optional intro scene flow before switching to the main scene.
- **Reaction Cam** — hotkey-friendly reaction mode concept for zoom/focus workflows.
- **Clean Recorder** — exports notes and session data into organized folders.
- **Built-in Soundpad** — trigger local audio files through OBS media sources.
- **Config Import/Export** — load and share creator presets.

### Not included

- YouTube title/description/tag generation.
- YouTube upload helpers.
- External analytics.

## Why this exists

OBS is powerful, but creators often need many small tools around it: notes for editing, sound buttons, panic actions, scene timers, and reusable setups. OBS ControlDeck brings those tools into one lightweight project.

## Quick start

1. Open OBS Studio.
2. Go to `Tools` -> `Scripts`.
3. Add `src/obs_controldeck.lua`.
4. Configure your output folder, scenes, sources, and sound files.
5. Assign hotkeys in OBS settings.
6. Start recording and use markers, notes, panic actions, and soundpad buttons.

More details are in [`docs/installation.md`](docs/installation.md) and [`docs/configuration.md`](docs/configuration.md).

## Presets

Example presets live in [`presets/`](presets/):

- `gaming.json`
- `podcast.json`
- `low-end-pc.json`
- `streamer.json`

Presets are meant to be safe to preview before applying. A preset should never silently overwrite everything without user awareness.

## Project status

Early development. The repository contains a working foundation and a clear roadmap, but some advanced behaviors may need adjustment depending on your OBS version, OS, and scene setup.

## Roadmap

### v0.1

- Lua script MVP
- Markers and clip notes
- Scene timer
- Basic soundpad
- Config import/export
- Example presets

### v0.2

- Better soundpack management
- Stronger Recording Guard checks
- Clean Recorder folder templates
- Improved panic actions

### v0.3

- Local browser control panel
- Reaction Cam automation
- Themeable interface
- Better preset preview

### v1.0

- Stable creator toolkit
- Full documentation
- Packaged releases
- Optional migration to native OBS plugin

## Repository layout

```txt
obs-controldeck/
├─ src/
│  └─ obs_controldeck.lua
├─ docs/
│  ├─ installation.md
│  ├─ configuration.md
│  ├─ soundpad.md
│  └─ presets.md
├─ presets/
│  ├─ gaming.json
│  ├─ podcast.json
│  ├─ low-end-pc.json
│  └─ streamer.json
├─ examples/
│  ├─ config-example.json
│  └─ markers-example.json
├─ sounds/
│  └─ README.md
├─ CHANGELOG.md
├─ CONTRIBUTING.md
└─ LICENSE
```

## License

MIT License. See [`LICENSE`](LICENSE).
