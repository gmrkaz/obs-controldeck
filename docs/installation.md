# Installation

## Requirements

- OBS Studio installed.
- Basic OBS scene/source setup.
- Local folder where OBS ControlDeck can write marker files.

## Install the Lua script

1. Download or clone this repository.
2. Open OBS Studio.
3. Go to `Tools` -> `Scripts`.
4. Press `+`.
5. Select `src/obs_controldeck.lua`.
6. Configure the script properties.
7. Open OBS hotkey settings and assign hotkeys for:
   - `ControlDeck: Add marker`
   - `ControlDeck: Panic Button`
   - `ControlDeck: Play Sound 1`
   - `ControlDeck: Play Sound 2`
   - `ControlDeck: Play Sound 3`
   - `ControlDeck: Play Sound 4`

## Recommended first setup

Create a folder such as:

```txt
OBS-ControlDeck-Sessions/
```

Use it as the output folder in the script settings.

Then configure:

- microphone source name;
- desktop audio source name;
- camera source name;
- panic/safe scene name;
- optional intro and main scene names;
- sound files for the soundpad.

## Notes

The first version is a Lua script foundation. Different OBS versions and operating systems may require small adjustments for media source behavior, especially the Soundpad module.
