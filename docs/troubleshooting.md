# Troubleshooting

## The script does not appear in OBS

Check that you added the file:

```txt
src/obs_controldeck.lua
```

through:

```txt
Tools -> Scripts -> +
```

If OBS shows a Lua error, open the OBS script log and copy the error into a GitHub issue.

## Marker files are not created

Check:

- the output folder is configured;
- OBS has permission to write to that folder;
- recording actually started and stopped;
- the script is still loaded.

## Soundpad does not play audio

Check:

- the sound file path is correct;
- the file exists locally;
- the file type is supported by OBS media sources;
- the slot volume is above `0`;
- OBS audio monitoring/output is configured correctly.

## Panic Button does not mute or hide sources

Check that source names match exactly.

OBS source names are case-sensitive in practice because the script searches by exact string.

Example:

```txt
Camera
```

is not the same as:

```txt
camera
```

## Recording Guard warns even though setup looks correct

Recording Guard uses the source names configured in the script properties.

If you renamed a source in OBS, update the script settings too.

## AutoIntro does not switch scenes

Check:

- `Enable AutoIntro` is enabled;
- Intro scene name is correct;
- Main scene name is correct;
- delay is between 1 and 60 seconds.

## Imported config does not apply

This is expected in v1.0.0. Import is preview-only for safety. The script logs the config preview so users can review it before future apply behavior exists.
