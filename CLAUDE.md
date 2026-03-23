# CLAUDE.md

This file provides guidance to Claude Code when building the `transcribe` project.

## Project

Single-file Python library and CLI (`transcribe.py`) that takes an audio or video file, extracts its audio, and transcribes it using local Whisper with word-level timestamps. Returns the raw Whisper result dict. No API calls.

**External requirements:** `ffmpeg` must be installed (`brew install ffmpeg`).

## Commands

```bash
# Install / sync dependencies
uv sync

# Install as a global CLI tool
uv pip install .
transcribe input.mp3

# Run directly
uv run python transcribe.py input.mp4
uv run python transcribe.py input.mp4 --model small

# Quick syntax check
uv run python -c "import ast, pathlib; ast.parse(pathlib.Path('transcribe.py').read_text()); print('OK')"
```

## Functions

Six functions plus one private helper in `transcribe.py`, in this order:

---

### `check_ffmpeg() -> None`

Verify that `ffmpeg` is available on PATH. If not found, print a styled error with Rich and exit with code 1.

```python
def check_ffmpeg() -> None:
    """Verify that ffmpeg is available on PATH; exit with a clear message if not."""
    if shutil.which("ffmpeg") is None:
        console.print(
            "[bold red]Error:[/bold red] ffmpeg was not found on your PATH.\n"
            "Please install ffmpeg (e.g. `brew install ffmpeg` on macOS) and try again."
        )
        sys.exit(1)
```

---

### `extract_audio(input_path: str, wav_path: str) -> None`

Use ffmpeg to extract and convert the input file to a 16 kHz mono WAV at `wav_path`. Suppress all ffmpeg stdout/stderr. Print progress with Rich.

```python
def extract_audio(input_path: str, wav_path: str) -> None:
    """Extract/convert input_path to a 16 kHz mono WAV at wav_path."""
    console.print(f"[cyan]Extracting audio from[/cyan] {input_path} …")
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    console.print(f"[green]Audio extracted →[/green] {wav_path}")
```

---

### `transcribe(wav_path: str, model_name: str) -> dict`

Load the Whisper model and transcribe the WAV file with word-level timestamps. Display a Rich spinner while running, with an elapsed `MM:SS` timer updated every second by a background thread. Return the raw Whisper result dict, or `{}` if no speech is detected.

**Whisper call parameters (exact):**
- `word_timestamps=True`
- `temperature=0.1`
- `condition_on_previous_text=False`
- `fp16=False`

**Segment count display:** After transcription, count punctuation-delimited segments (words ending in `.,;?!`) and print the count. Add 1 for any trailing word without punctuation.

---

### `format_transcript(result: dict, plain: bool = False) -> str`

Formats the Whisper result into one sentence per line with a `MM:SS` timestamp prefix. Uses word-level data to detect sentence boundaries (words ending in `.?!`). Calls `_fix_spacing()` on each sentence.

- `plain=False` (default): timestamps are wrapped in Rich `[dim]...[/dim]` markup for terminal display.
- `plain=True`: timestamps are bare text, suitable for file export.

Returns an empty string if `result` is empty.

---

### `_fix_spacing(text: str) -> str`

Private helper. Removes spurious spaces before apostrophes in contractions (e.g. French `c 'est` → `c'est`) using a regex substitution.

---

### `export_transcript(result: dict, output_path: str) -> None`

Writes the raw Whisper result dict to a JSON file at `output_path`. Prints a Rich confirmation line on success.

---

## Return value

`transcribe()` returns the raw dict from `model.transcribe()`. The structure is:

```python
{
    "text": "full transcript as a string",
    "segments": [
        {
            "id": 0,
            "start": 0.0,
            "end": 2.5,
            "text": " Hello world.",
            "words": [
                {"word": " Hello", "start": 0.0, "end": 0.5, "probability": 0.99},
                {"word": " world.", "start": 0.6, "end": 1.2, "probability": 0.98},
            ]
        },
        ...
    ],
    "language": "en"
}
```

Returns `{}` when no speech is detected.

---

## CLI entry point (`main`)

The CLI accepts an input file, an optional `--model` flag, and an optional `--output-format` flag.

- **Default (no `--output-format`):** pretty-print the transcript to the terminal using `format_transcript()`.
- **`--output-format raw`:** export the raw Whisper JSON to `<input>.json` using `export_transcript()`.
- **`--output-format txt`:** export a plain-text formatted transcript to `<input>.txt` using `format_transcript(plain=True)`.

```
transcribe input.mp3
transcribe input.mp4 --model small
transcribe input.mp3 --output-format raw
transcribe input.mp3 --output-format txt
```

**Pipeline in `main()`:**

1. Call `check_ffmpeg()`
2. Validate the input file exists
3. Validate the input file extension is supported; exit with error if not
4. If input is `.wav`, use it directly; otherwise call `extract_audio()` into a `tempfile.mkstemp(suffix=".wav")` path
5. Call `transcribe(wav_path, model_name)`
6. If `--output-format raw`: call `export_transcript(result, output_path)` where `output_path` is the input path with `.json` extension
7. If `--output-format txt`: write `format_transcript(result, plain=True)` to `<input>.txt`
8. Otherwise: call `format_transcript(result)` and print it with Rich
9. Delete the temp WAV in a `finally` block

**Supported input extensions:** `.mp3`, `.mp4`, `.mov`, `.mkv`, `.m4a`, `.aac`, `.wav`

---

## CLI arguments

| Arg | Default | Description |
|---|---|---|
| `input` | — | Input audio or video file |
| `--model` | `turbo` | Whisper model size (tiny/base/small/medium/large/turbo) |
| `--output-format` | `None` | Export format: `raw` (JSON) or `txt` (plain text). Omit to print to terminal. |

---

## Package / installation

`pyproject.toml` — use hatchling, include only `transcribe.py` in the wheel, entry point `transcribe`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "transcribe"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "openai-whisper",
    "rich",
]

[project.scripts]
transcribe = "transcribe:main"

[tool.hatch.build.targets.wheel]
include = ["transcribe.py"]
```

## Imports

```python
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import whisper
from rich.console import Console

console = Console()
```

## Verification

```bash
# Syntax check
uv run python -c "import ast, pathlib; ast.parse(pathlib.Path('transcribe.py').read_text()); print('OK')"

# Run on a test audio file
uv run python transcribe.py test.mp3

# Run on a test video file with a smaller model
uv run python transcribe.py test.mp4 --model small

# Export formats
uv run python transcribe.py test.mp3 --output-format txt
uv run python transcribe.py test.mp3 --output-format raw
```
