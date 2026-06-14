# Release checklist

Use this checklist before publishing a GitHub release.

## Script checks

- [ ] `src/obs_controldeck.lua` loads in OBS without Lua errors.
- [ ] Script settings are visible.
- [ ] Hotkeys can be assigned.
- [ ] Recording start adds a `Start` marker.
- [ ] Recording stop exports `.txt` and `.json` marker files.
- [ ] Scene changes update scene totals.
- [ ] Panic Button mutes the configured mic.
- [ ] Panic Button switches to the configured safe scene.
- [ ] Soundpad slots play local test audio.
- [ ] Config export creates a JSON file.
- [ ] Config import preview writes to the OBS log without applying changes.

## Documentation checks

- [ ] README shows the correct version.
- [ ] `VERSION` matches the script version.
- [ ] CHANGELOG contains the release.
- [ ] RELEASE_NOTES are updated.
- [ ] Installation docs are current.
- [ ] Soundpad docs mention no copyrighted sounds.
- [ ] Preset schema matches examples.

## GitHub release checks

- [ ] Create tag `v1.0.0`.
- [ ] Create GitHub release named `OBS ControlDeck v1.0.0`.
- [ ] Attach `src/obs_controldeck.lua` as a release asset if desired.
- [ ] Link to `RELEASE_NOTES.md`.
- [ ] Add screenshots or a GIF when available.
