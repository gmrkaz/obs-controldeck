# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 1.0.x | Yes |

## Reporting a vulnerability

Please open a private security report if available on GitHub, or create an issue with minimal public details and request maintainer contact.

Do not publish exploit details for issues involving:

- unsafe file handling;
- config import behavior;
- path traversal;
- unexpected OBS automation;
- malicious preset behavior.

## Config safety principles

OBS ControlDeck should treat third-party presets as untrusted input.

Stable behavior:

- imported configs are previewed before being applied;
- third-party configs should not silently overwrite OBS scenes or sources;
- users should be able to review changed sections;
- public presets should avoid absolute local file paths when possible.
