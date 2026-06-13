# Presets

Presets are shareable configuration files for OBS ControlDeck.

## Goals

Presets should help creators quickly switch between workflows:

- gaming recording;
- podcast recording;
- low-end PC setup;
- streaming setup;
- shorts/highlight workflow.

## Safety model

Imported presets should not silently overwrite everything.

Recommended future flow:

```txt
1. Select preset file.
2. Preview changes.
3. Choose which sections to import.
4. Apply selected settings.
5. Save backup of previous settings.
```

## Preset sections

A preset may contain:

- profile name;
- source names;
- scene names;
- hotkeys;
- soundpad slots;
- marker categories;
- Recording Guard rules;
- AutoIntro settings;
- Panic Button settings.

## Example

```json
{
  "profileName": "Gaming Stream Setup",
  "version": "1.0.0",
  "hotkeys": {
    "addMarker": "F6",
    "panicButton": "F10"
  },
  "soundpad": {
    "enabled": true,
    "volume": 75
  }
}
```
