# Configuration

OBS ControlDeck is configured inside OBS through the script properties panel.

## Core settings

| Setting | Description |
| --- | --- |
| Output folder | Folder where marker and session files are saved. |
| Default marker note | Text used when adding a marker through the hotkey. |
| Default marker type | Marker category: Highlight, Funny, Cut, Mistake, Audio, Panic, or Custom. |

## Recording Guard

Recording Guard checks common problems when recording starts.

Recommended source names:

```txt
Microphone/Aux
Desktop Audio
Camera
```

If your sources have different names, copy the exact names from OBS.

## Panic Button

The Panic Button can:

- add a panic marker;
- mute the configured microphone source;
- hide the configured camera source in the current scene;
- stop soundpad media sources;
- switch to a safe scene.

Recommended safe scene names:

```txt
BRB
Safe
Starting Soon
Pause
```

## AutoIntro

AutoIntro can switch to an intro scene when recording starts, wait a few seconds, then switch to your main scene.

Example:

```txt
Intro scene: Intro
Main scene: Gameplay
Delay: 5 seconds
```

## Config import/export

The export button writes a JSON-style preset with current ControlDeck settings.

The import button in v0.1 only previews the config in the OBS script log. This is intentional: imported configs should not silently overwrite a creator's OBS setup.

Future versions will add a safer apply flow:

```txt
Preview changes -> Select what to import -> Apply selected settings
```
