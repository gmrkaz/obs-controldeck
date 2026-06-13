# Soundpad

OBS ControlDeck includes a simple soundpad foundation.

## What it does

Each sound slot has:

- title;
- local audio file;
- volume;
- hotkey.

Supported file types in the UI filter:

```txt
.mp3
.wav
.ogg
.flac
```

## How it works

The Lua script creates OBS media sources for sound slots and restarts them when a sound hotkey is pressed.

Current MVP slots:

```txt
Sound 1
Sound 2
Sound 3
Sound 4
```

## Sound packs

A future version will support full sound packs like this:

```json
{
  "name": "Streamer Pack",
  "sounds": [
    {
      "title": "Vine Boom",
      "file": "sounds/vine-boom.mp3",
      "hotkey": "F1",
      "volume": 80
    }
  ]
}
```

## Important note

Do not commit copyrighted sound files to this repository unless you have permission. Use the `sounds/` folder for your own local files or placeholder documentation.
