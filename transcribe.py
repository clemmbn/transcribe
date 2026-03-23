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


def check_ffmpeg() -> None:
    """Verify that ffmpeg is available on PATH; exit with a clear message if not."""
    if shutil.which("ffmpeg") is None:
        console.print(
            "[bold red]Error:[/bold red] ffmpeg was not found on your PATH.\n"
            "Please install ffmpeg (e.g. `brew install ffmpeg` on macOS) and try again."
        )
        sys.exit(1)


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


def transcribe(wav_path: str, model_name: str) -> dict:
    """Transcribe wav_path with Whisper and print the segment count."""
    console.print(f"[cyan]Loading Whisper model[/cyan] '{model_name}' …")
    model = whisper.load_model(model_name)

    with console.status(f"[cyan]Transcribing audio using whisper {model_name} …[/cyan]", spinner="dots") as status:
        _t0 = time.monotonic()

        def _tick():
            elapsed = time.monotonic() - _t0
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
            _elapsed = time.monotonic() - _t0

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


def format_transcript(result: dict, plain: bool = False) -> str:
    """Format a Whisper result dict into one sentence per line with timestamps."""
    if not result:
        return ""
    all_words = [
        word
        for seg in result.get("segments", [])
        for word in seg.get("words", [])
    ]
    if not all_words:
        return result.get("text", "").strip()

    SENT_END = set(".?!")
    lines = []
    sentence_words = []
    sentence_start = None

    for w in all_words:
        text = w["word"]
        if sentence_start is None:
            sentence_start = w["start"]
        sentence_words.append(text.strip())
        if text.rstrip() and text.rstrip()[-1] in SENT_END:
            m, s = divmod(int(sentence_start), 60)
            ts = f"{m:02d}:{s:02d}"
            prefix = ts if plain else f"[dim]{ts}[/dim]"
            lines.append(f"{prefix}  {_fix_spacing(' '.join(sentence_words))}")
            sentence_words = []
            sentence_start = None

    if sentence_words:
        m, s = divmod(int(sentence_start), 60)
        ts = f"{m:02d}:{s:02d}"
        prefix = ts if plain else f"[dim]{ts}[/dim]"
        lines.append(f"{prefix}  {_fix_spacing(' '.join(sentence_words))}")

    return "\n".join(lines)


def _fix_spacing(text: str) -> str:
    """Remove spurious spaces before apostrophes in contractions (e.g. French 'c 'est' → 'c'est')."""
    return re.sub(r"(\w) (['''])(\w)", r"\1\2\3", text)


def export_transcript(result: dict, output_path: str) -> None:
    """Write the raw Whisper result dict to a JSON file at output_path."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    console.print(f"[green]Raw transcript exported →[/green] {output_path}")


def main():
    SUPPORTED_EXTENSIONS = {".mp3", ".mp4", ".mov", ".mkv", ".m4a", ".aac", ".wav"}

    parser = argparse.ArgumentParser(description="Transcribe audio or video files using Whisper.")
    parser.add_argument("input", help="Input audio or video file")
    parser.add_argument("--model", default="turbo", help="Whisper model size (tiny/base/small/medium/large/turbo). Default: turbo")
    parser.add_argument("--output-format", choices=["raw", "txt"], default=None, help="Export format: 'raw' (JSON) or 'txt' (pretty text). Omit to print to terminal.")
    args = parser.parse_args()

    check_ffmpeg()

    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[bold red]Error:[/bold red] File not found: {input_path}")
        sys.exit(1)

    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        console.print(
            f"[bold red]Error:[/bold red] Unsupported file extension '{input_path.suffix}'.\n"
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
        sys.exit(1)

    tmp_wav = None
    try:
        if input_path.suffix.lower() == ".wav":
            wav_path = str(input_path)
        else:
            fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            extract_audio(str(input_path), tmp_wav)
            wav_path = tmp_wav

        result = transcribe(wav_path, args.model)
        if result:
            if args.output_format == "raw":
                export_transcript(result, str(input_path.with_suffix(".json")))
            elif args.output_format == "txt":
                output_path = str(input_path.with_suffix(".txt"))
                Path(output_path).write_text(format_transcript(result, plain=True), encoding="utf-8")
                console.print(f"[green]Transcript exported →[/green] {output_path}")
            else:
                console.print()
                console.print(format_transcript(result))
    finally:
        if tmp_wav:
            Path(tmp_wav).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
