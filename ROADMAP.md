# Roadmap

This roadmap keeps OBS ControlDeck focused, testable, and easy to release. The project starts as a lightweight OBS Lua toolkit, then grows toward a cleaner control-panel workflow.

## Current focus

**Goal:** make the Lua version stable enough for real recording sessions.

- Keep setup simple through `Tools -> Scripts` in OBS Studio.
- Avoid external services, accounts, uploads, and bundled copyrighted sounds.
- Make every recording helper safe, local, and understandable.
- Prefer reliable core features over a large unfinished feature set.

## v0.1 - Foundation

Status: mostly planned/implemented foundation.

- OBS Lua script foundation.
- Recording markers.
- Clip notes.
- Scene timer.
- Panic Button.
- Recording Guard.
- Basic Soundpad slots.
- Config export.
- Safe config import preview.

## v0.2 - Better creator workflow

Status: next practical milestone.

- Add cleaner session folder creation.
- Improve marker export formatting.
- Add more Recording Guard checks.
- Improve media source cleanup after soundpad playback.
- Add better preset validation errors.
- Add more sound slots without making the UI confusing.
- Document recommended OBS hotkeys.

## v0.3 - Control panel prototype

Status: future milestone.

- Local browser panel concept.
- Phone-friendly button layout.
- Scene switching panel.
- Soundpad grid.
- Marker buttons.
- Panic Button confirmation/safety behavior.

## v0.4 - Testing and examples

Status: future milestone.

- Add example marker exports.
- Add example preset files.
- Add a manual testing checklist.
- Add release checklist.
- Add screenshots or GIFs for the README.

## v1.0 - Stable creator release

Status: release target.

- Packaged release archive.
- Full installation docs.
- Full configuration docs.
- Tested presets.
- Safe import/apply flow.
- Clean changelog and release notes.

## Later ideas

These are intentionally not part of the first stable release:

- Native OBS plugin packaging.
- Advanced dock UI.
- Stream deck integrations.
- Cloud sync.
- YouTube upload helpers.
- AI-generated titles, descriptions, or tags.
