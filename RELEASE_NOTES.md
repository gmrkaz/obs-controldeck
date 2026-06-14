# OBS ControlDeck v1.0.0

OBS ControlDeck v1.0.0 is the first stable Lua-script release of the creator toolkit for OBS Studio.

## Highlights

- Timestamped recording markers.
- Clip note categories for editing workflows.
- Scene Timer session tracking.
- Panic Button for creator safety workflows.
- Recording Guard setup checks.
- AutoIntro scene switching.
- Reaction marker hotkey.
- Built-in Soundpad with 8 configurable slots.
- JSON and TXT marker exports.
- Config export and safe import preview.
- Example presets for gaming, podcast, and streaming setups.

## Install

1. Download the repository.
2. Open OBS Studio.
3. Go to `Tools` -> `Scripts`.
4. Add `src/obs_controldeck.lua`.
5. Configure sources, scenes, output folder, and sound slots.
6. Assign OBS hotkeys.

## Recommended hotkeys

| Action | Suggested key |
| --- | --- |
| Add marker | F6 |
| Reaction marker | F7 |
| Panic Button | F10 |
| Soundpad slots | Numpad 1-8 |

## Safety notes

- The project does not include copyrighted sound files.
- Imported third-party configs are previewed instead of silently applied.
- Panic Button behavior depends on source names configured by the user.

## Known limitations

- This is a Lua script release, not a native OBS plugin.
- Config import is preview-only in v1.0.0.
- Soundpad behavior can vary depending on OBS media source support and OS audio setup.

## Next

The next milestone should focus on:

- preset apply wizard;
- local control panel;
- better soundpack manager;
- screenshots and demo GIFs;
- packaged GitHub release assets.
