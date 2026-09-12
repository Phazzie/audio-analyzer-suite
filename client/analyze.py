#!/usr/bin/env python3
"""
Audio Analyzer Client
Sends local audio files (.mp3, .wav, .flac) to RunPod Serverless for AI music analysis.
"""

import os
import sys
import json
import base64
import argparse
from pathlib import Path

try:
    import runpod
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    console = Console()
except ImportError:
    console = None

def get_api_key():
    """Retrieve API key from env or ~/.runpod/config.toml."""
    if os.environ.get("RUNPOD_API_KEY"):
        return os.environ["RUNPOD_API_KEY"]
    
    config_file = Path.home() / ".runpod" / "config.toml"
    if config_file.exists():
        try:
            for line in config_file.read_text().splitlines():
                if "apikey" in line:
                    return line.split("=")[1].strip().strip("'\"")
        except Exception:
            pass
    return None

def format_seconds(secs):
    mins = int(secs // 60)
    remainder = round(secs % 60, 1)
    return f"{mins}m {remainder}s"

def print_rich_report(data, filename):
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]AI Music & Audio Analysis Report[/bold cyan]\n[yellow]{filename}[/yellow]",
        border_style="cyan"
    ))

    # 1. Metadata & Musical Analysis
    meta = data.get("metadata", {})
    music = data.get("musical_analysis", {})
    eng = data.get("audio_engineering", {})

    t1 = Table(title="[bold green]Musical Analysis[/bold green]", show_header=True, header_style="bold magenta")
    t1.add_column("Property", style="cyan", width=25)
    t1.add_column("Detected Value", style="bold white")

    t1.add_row("Duration", format_seconds(meta.get("duration_seconds", 0)))
    t1.add_row("Estimated Key", f"[bold green]{music.get('key', 'Unknown')}[/bold green] (confidence: {music.get('key_confidence', 0)})")
    t1.add_row("Tempo (BPM)", f"[bold yellow]{music.get('bpm', 0)} BPM[/bold yellow]")
    t1.add_row("Total Beats Counted", str(music.get("detected_beats_count", 0)))
    
    chords_summary = " -> ".join(music.get("chord_progression_summary", [])[:8])
    t1.add_row("Primary Progression", f"[magenta]{chords_summary}[/magenta]")
    console.print(t1)

    # 2. Structural Breakdown Table
    struct = data.get("structure_analysis", {})
    sections = struct.get("sections", [])
    if sections:
        console.print()
        t2 = Table(title="[bold green]Song Structural Sections[/bold green]", show_header=True, header_style="bold blue")
        t2.add_column("Section Label", style="bold white")
        t2.add_column("Start Time", style="cyan")
        t2.add_column("End Time", style="cyan")
        t2.add_column("Duration", style="yellow")
        t2.add_column("Relative Energy", style="magenta")

        for s in sections:
            t2.add_row(
                s.get("section", "Section"),
                f"{s.get('start_time', 0):.1f}s",
                f"{s.get('end_time', 0):.1f}s",
                f"{s.get('duration', 0):.1f}s",
                s.get("relative_energy", "Medium")
            )
        console.print(t2)

    # 3. Audio Engineering & Dynamics Table
    if eng:
        console.print()
        t3 = Table(title="[bold green]Audio Engineering & Dynamics[/bold green]", show_header=True, header_style="bold yellow")
        t3.add_column("Acoustic Metric", style="cyan", width=25)
        t3.add_column("Measurement", style="bold white")

        t3.add_row("Average Loudness", f"{eng.get('average_rms_dbfs', 0)} dBFS")
        t3.add_row("Peak Level", f"{eng.get('peak_dbfs', 0)} dBFS")
        t3.add_row("Dynamic Range", f"{eng.get('dynamic_range_db', 0)} dB")
        t3.add_row("Dynamics Profile", f"[bold]{eng.get('dynamics_profile', 'Standard')}[/bold]")
        t3.add_row("Spectral Brightness", f"{eng.get('spectral_brightness_hz', 0)} Hz (Centroid)")
        t3.add_row("High-Freq Rolloff", f"{eng.get('spectral_rolloff_hz', 0)} Hz")
        console.print(t3)

    console.print("\n[bold green]✓ Analysis Completed Successfully![/bold green]\n")

def main():
    parser = argparse.ArgumentParser(description="Analyze local audio files using RunPod Serverless")
    parser.add_argument("audio_file", help="Path to local audio file (.mp3, .wav, .flac, .ogg)")
    parser.add_argument("--endpoint", "-e", default=os.environ.get("RUNPOD_ENDPOINT_ID"), help="RunPod Serverless Endpoint ID")
    parser.add_argument("--api-key", "-k", default=get_api_key(), help="RunPod API Key")
    parser.add_argument("--output", "-o", help="Optional path to save full JSON report")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON to stdout")

    args = parser.parse_args()

    audio_path = Path(args.audio_file).expanduser().resolve()
    if not audio_path.is_file():
        print(f"Error: File not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    if not args.endpoint:
        print("Error: RunPod Endpoint ID not provided.", file=sys.stderr)
        print("Specify with --endpoint <ID> or set export RUNPOD_ENDPOINT_ID='<ID>'", file=sys.stderr)
        sys.exit(1)

    if not args.api_key:
        print("Error: RunPod API key not found. Run 'runpodctl doctor' or export RUNPOD_API_KEY.", file=sys.stderr)
        sys.exit(1)

    # 1. Read & encode audio bytes
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    if console:
        console.print(f"[cyan]Encoding local audio:[/cyan] [yellow]{audio_path.name}[/yellow] ({file_size_mb:.2f} MB)...")
    
    with open(audio_path, "rb") as f:
        b64_audio = base64.b64encode(f.read()).decode("utf-8")

    # 2. Call RunPod Serverless Endpoint
    runpod.api_key = args.api_key
    endpoint = runpod.Endpoint(args.endpoint)

    if console:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Dispatching to RunPod Serverless GPU & analyzing track...[/bold cyan]"),
            transient=True
        ) as progress:
            progress.add_task("analyzing", total=None)
            response = endpoint.run_sync({
                "audio_base64": b64_audio,
                "filename": audio_path.name
            })
    else:
        print("Dispatching to RunPod Serverless GPU...")
        response = endpoint.run_sync({
            "audio_base64": b64_audio,
            "filename": audio_path.name
        })

    # 3. Check for errors
    if "error" in response:
        print(f"Serverless Error: {response['error']}", file=sys.stderr)
        sys.exit(1)

    output = response.get("output", response)
    if output.get("status") == "error":
        print(f"Analysis Failed: {output.get('message')}", file=sys.stderr)
        sys.exit(1)

    # 4. Display or save output
    if args.output:
        with open(args.output, "w") as out_f:
            json.dump(output, out_f, indent=2)
        if console:
            console.print(f"[green]Saved detailed JSON output to: {args.output}[/green]")

    if args.raw or not console:
        print(json.dumps(output, indent=2))
    else:
        print_rich_report(output, audio_path.name)

if __name__ == "__main__":
    main()
