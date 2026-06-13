# Contributing

Thanks for helping improve OBS ControlDeck.

## Good first contributions

- Test the Lua script on your OBS setup.
- Improve documentation.
- Add safe preset examples.
- Add better config validation.
- Improve Soundpad source handling.
- Add screenshots or demo GIFs.

## Development notes

This project starts as an OBS Lua script. Keep changes simple and easy to test.

Before opening a pull request:

1. Test script loading in OBS.
2. Check that OBS does not show Lua errors.
3. Test markers while recording.
4. Test soundpad with a local audio file.
5. Update documentation if behavior changes.

## Preset safety

Config import must be safe. Do not add behavior that silently overwrites a user's OBS setup without a preview or clear warning.
