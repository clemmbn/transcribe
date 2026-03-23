# transcribe

CLI tool that transcribes audio and video files locally using [Whisper](https://github.com/openai/whisper). No API calls, runs entirely on your machine.

## Requirements

- Python 3.14+
- [ffmpeg](https://ffmpeg.org/) — `brew install ffmpeg`

## Installation

```bash
uv pip install .
```

Or run directly without installing:

```bash
uv run python transcribe.py input.mp3
```

## Usage

```bash
# Print transcript to terminal
transcribe input.mp3

# Use a specific Whisper model (default: turbo)
transcribe input.mp4 --model small

# Export as plain text file → input.txt
transcribe input.mp3 --output-format txt

# Export raw Whisper JSON → input.json
transcribe input.mp3 --output-format raw
```

## Options

| Option | Default | Description |
|---|---|---|
| `--model` | `turbo` | Whisper model: `tiny`, `base`, `small`, `medium`, `large`, `turbo` |
| `--output-format` | — | `txt` to save as text file, `raw` to save as JSON |

## Supported formats

`.mp3`, `.mp4`, `.mov`, `.mkv`, `.m4a`, `.aac`, `.wav`

## Output

By default, the transcript is printed to the terminal with sentence-level timestamps:

```
00:00  Hello, welcome to the recording.
00:04  Today we'll be covering the main topics.
```
