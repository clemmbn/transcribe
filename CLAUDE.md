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

## Functions to implement

Implement exactly five functions in `transcribe.py`, in this order:

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

Load the Whisper model and transcribe the WAV file with word-level timestamps. Display a Rich spinner while running, with an elapsed `MM:SS` timer updated every second by a background thread (Whisper has no progress callback). Return the raw Whisper result dict, or `{}` if no speech is detected.

**Whisper call parameters (exact):**
- `word_timestamps=True`
- `temperature=0.1`
- `condition_on_previous_text=False`
- `fp16=False`

**Segment count display:** After transcription, count punctuation-delimited segments (words ending in `.,;?!`) and print the count. Add 1 for any trailing word without punctuation.

```python
def transcribe(wav_path: str, model_name: str) -> dict:
    """Transcribe wav_path with Whisper and print the segment count."""
    console.print(f"[cyan]Loading Whisper model[/cyan] '{model_name}' …")
    model = whisper.load_model(model_name)

    with console.status(f"[cyan]Transcribing audio using whisper {model_name} …[/cyan]", spinner="dots") as status:
        import time as _time

        _t0 = _time.monotonic()

        def _tick():
            elapsed = _time.monotonic() - _t0
            m, s = divmod(int(elapsed), 60)
            status.update(f"[cyan]Transcribing audio using whisper {model_name} …[/cyan]  [dim]{m:02d}:{s:02d}[/dim]")

        _stop = threading.Event()

        def _timer():
            while not _stop.wait(1):
                _tick()

        _t = threading.Thread(target=_timer, daemon=True)
        _t.start()

        try:
            result = model.transcribe(
                wav_path,
                word_timestamps=True,
                temperature=0.1,
                condition_on_previous_text=False,
                fp16=False,
            )
        finally:
            _stop.set()
            _t.join()
            _elapsed = _time.monotonic() - _t0

    _em, _es = divmod(int(_elapsed), 60)

    all_words = [
        word
        for seg in result.get("segments", [])
        for word in seg.get("words", [])
    ]

    if not all_words:
        console.print(f"[green]Transcription complete in {_em:02d}:{_es:02d}.[/green] No speech detected.")
        return {}

    PUNCT = set(".,;?!")
    count = sum(
        1 for w in all_words if w["word"].rstrip() and w["word"].rstrip()[-1] in PUNCT
    )
    if all_words and (not all_words[-1]["word"].rstrip() or all_words[-1]["word"].rstrip()[-1] not in PUNCT):
        count += 1

    console.print(f"[green]Transcription complete in {_em:02d}:{_es:02d}.[/green] {count} segment(s) found.")
    return result
```

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

## Additional functions

### `format_transcript(result: dict) -> str`

Formats the Whisper result into a human-readable string for terminal display. Joins segment texts, trims whitespace, and returns a clean string. Returns an empty string if `result` is empty.

### `export_transcript(result: dict, output_path: str) -> None`

Writes the raw Whisper result dict to a JSON file at `output_path`. Prints a Rich confirmation line on success.

---

## CLI entry point (`main`)

The CLI accepts an input file, an optional `--model` flag, and an optional `-r` / `--raw` flag.

- **Default (no `-r`):** pretty-print the transcript to the terminal using `format_transcript()`.
- **With `-r`:** export the raw Whisper JSON to a file named after the input (e.g. `input.mp3` → `input.json`) using `export_transcript()`.

```
transcribe input.mp3
transcribe input.mp4 --model small
transcribe input.mp3 -r
transcribe -r input.mp3 --model small
```

**Pipeline in `main()`:**

1. Call `check_ffmpeg()`
2. Validate the input file exists
3. If input is `.wav`, use it directly; otherwise call `extract_audio()` into a `tempfile.mktemp(suffix=".wav")` path
4. Call `transcribe(wav_path, model_name)`
5. If `-r`: call `export_transcript(result, output_path)` where `output_path` is the input path with `.json` extension
6. Otherwise: call `format_transcript(result)` and print it with Rich
7. Delete the temp WAV in a `finally` block

**Supported input extensions:** `.mp3`, `.mp4`, `.mov`, `.mkv`, `.m4a`, `.aac`, `.wav`

---

## CLI arguments

| Arg | Default | Description |
|---|---|---|
| `input` | — | Input audio or video file |
| `--model` | `medium` | Whisper model size (tiny/base/small/medium/large) |
| `-r` / `--raw` | `False` | Export raw Whisper JSON to `<input>.json` instead of pretty-printing |

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

The file uses only stdlib and the two dependencies:

```python
import argparse
import shutil
import subprocess
import sys
import tempfile
import threading
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
```
