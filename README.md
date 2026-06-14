# OBS ControlDeck

> A creator-focused control toolkit for OBS Studio.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![OBS](https://img.shields.io/badge/OBS-Studio-302E31)
![Lua](https://img.shields.io/badge/script-Lua-2C2D72)
![License](https://img.shields.io/badge/license-Source--Available-red)

**OBS ControlDeck** is a source-available toolkit for OBS Studio that adds recording markers, timestamped clip notes, scene timers, panic actions, recording checks, a built-in soundpad, local presets, and safe config sharing.

It is designed for creators who record gameplay, tutorials, podcasts, reactions, highlights, streams, and long-form videos.

## v1.0.0 release

The first stable release is focused on a lightweight OBS Lua workflow:

- easy install through `Tools -> Scripts`;
- no external account required;
- no YouTube helper or upload automation;
- no bundled copyrighted sounds;
- safe preset import preview before applying anything.

## Core features

### AutoMarker

Add timestamped markers while recording. Each marker includes:

- time from recording start;
- marker type;
- note;
- current scene;
- creation time.

### ClipNotes

Create editing notes such as:

- Highlight;
- Funny;
- Mistake;
- Audio;
- Panic;
- Reaction;
- Custom.

Exports are saved as both `.txt` and `.json`.

### Scene Timer

Track how long each scene was active during a recording session.

### Panic Button

One hotkey can:

- add a panic marker;
- mute a configured microphone source;
- hide a configured camera source in the current scene;
- stop active soundpad media sources;
- switch to a configured safe scene.

### Recording Guard

When recording starts, OBS ControlDeck checks common setup problems:

- output folder missing;
- microphone source missing;
- microphone muted;
- desktop audio source missing;
- desktop audio muted;
- no active scene detected.

### AutoIntro

Optionally switch to an intro scene when recording starts, wait a few seconds, then switch to your main scene.

### Reaction Marker

A dedicated reaction hotkey can mark moments that should become reaction clips later.

### Built-in Soundpad

Trigger local audio files from OBS using hotkeys. The v1.0.0 script includes eight configurable sound slots.

Supported local file types in the UI filter:

```txt
.mp3
.wav
.ogg
.flac
```

### Config import/export

Export your current ControlDeck setup to a JSON-style preset. Import preview is intentionally safe: v1.0.0 reads and previews config text in the OBS script log instead of silently overwriting your setup.

## Quick start

1. Download or clone this repository.
2. Open OBS Studio.
3. Go to `Tools` -> `Scripts`.
4. Add `src/obs_controldeck.lua`.
5. Configure your output folder, scenes, sources, and sound files.
6. Assign hotkeys in OBS settings.
7. Start recording and use markers, notes, panic actions, and soundpad buttons.

Detailed setup:

- [`docs/installation.md`](docs/installation.md)
- [`docs/configuration.md`](docs/configuration.md)
- [`docs/soundpad.md`](docs/soundpad.md)
- [`docs/presets.md`](docs/presets.md)
- [`docs/troubleshooting.md`](docs/troubleshooting.md)

## Recommended OBS hotkeys

| Action | Suggested key |
| --- | --- |
| Add marker | F6 |
| Reaction marker | F7 |
| Panic Button | F10 |
| Sound 1-8 | Numpad 1-8 |

## Output files

After a session, OBS ControlDeck writes files like:

```txt
2026-06-14_20-30-10-markers.txt
2026-06-14_20-30-10-markers.json
```

Example JSON:

```json
{
  "version": "1.0.0",
  "markers": [
    {
      "time": "00:02:13",
      "seconds": 133,
      "type": "Highlight",
      "scene": "Gameplay",
      "note": "Good moment"
    }
  ],
  "sceneTotals": {
    "Gameplay": 133
  }
}
```

## Presets

Example presets live in [`presets/`](presets/):

- `gaming.json`
- `podcast.json`
- `streamer.json`

Preset schema:

- [`schema/control-deck-preset.schema.json`](schema/control-deck-preset.schema.json)

## Repository layout

```txt
obs-controldeck/
├─ src/
│  └─ obs_controldeck.lua
├─ docs/
│  ├─ installation.md
│  ├─ configuration.md
│  ├─ soundpad.md
│  ├─ presets.md
│  ├─ troubleshooting.md
│  └─ release-checklist.md
├─ schema/
│  └─ control-deck-preset.schema.json
├─ presets/
│  ├─ gaming.json
│  ├─ podcast.json
│  └─ streamer.json
├─ examples/
│  ├─ config-example.json
│  └─ markers-example.json
├─ sounds/
│  └─ README.md
├─ RELEASE_NOTES.md
├─ CHANGELOG.md
├─ VERSION
├─ SECURITY.md
├─ CONTRIBUTING.md
└─ LICENSE
```

## What is intentionally not included

- YouTube title/description/tag generation.
- YouTube upload helpers.
- Bundled copyrighted sound files.
- Silent config overwrite from third-party presets.

## Status

**Stable v1.0.0 foundation.** Advanced UI panels and native plugin packaging are planned after the Lua release.

## License

OBS ControlDeck is **source-available, not open-source**.

You may view the code, use it personally, and fork it only to propose changes back to the original project. You may not copy, redistribute, sell, rebrand, publish modified versions, or use the project commercially without written permission from the copyright holder.

See [`LICENSE`](LICENSE) for the full terms.
