# Product Requirements Document (PRD)
## AI Music Analysis Suite & Modular Extensibility Engine

**Document Status**: Proposed  
**Author**: Antigravity & User  
**Version**: 1.0.0  
**Target Repository**: [Phazzie/audio-analyzer-suite](https://github.com/Phazzie/audio-analyzer-suite)  

---

## 1. Executive Summary & Problem Statement

Modern music production, audio engineering, and catalog analysis require multifaceted audio processing: musical structure (chords, key, tempo, sections), sound engineering (LUFS loudness, spectral balance, dynamic range, phase correlation), source separation (stems), and intelligent mix critique. 

Currently, these capabilities exist scattered across fragmented tools, heavy desktop DAWs, or disparate AI research repos. 

**The Goal**: Build a unified, automated music analysis system that accepts local `.wav` and `.mp3` files, executes a battery of analysis models and audio DSP tools, and presents a clean, consolidated report with isolated stems and MIDI. 

**Core Architectural Mandate**: The system must be **easily expandable**—developers and users must be able to add new models, DSP tools, and plugins without needing to rebuild or push multi-gigabyte Docker containers every time a feature is added or modified.

---

## 2. User Personas & Use Cases

* **Music Producer / Songwriter**: Drops in a rough demo or reference track to automatically detect tempo changes, extract chord charts / lead sheets to MIDI, and break down the song arrangement into verse/chorus boundaries.
* **Mixing & Mastering Engineer**: Runs a final mix to check integrated LUFS, peak clipping, phase correlation across frequency bands, and receive an AI-driven mix critique comparing low-end clarity and vocal placement against industry standards.
* **Sample Hunter / Remixer**: Extracts clean 6-stem separations (vocals, drums, bass, guitar, piano, other) from full tracks with zero local GPU strain.
* **Audio AI Developer**: Rapidly tests and integrates newly released Hugging Face models or custom Python DSP scripts by simply dropping a `.py` file into a plugins directory.

---

## 3. Functional Requirements

### FR-1: Audio Ingestion & Handling
* Ingest standard audio formats (`.mp3`, `.wav`, `.flac`, `.aiff`, `.ogg`).
* Support files up to 150 MB (approx. 15-minute high-res stems or full-length tracks).
* Client-side audio validation (bitrate, sample rate, channel count, duration).

### FR-2: Modular Analysis Engine
The analysis pipeline must support modular analyzers categorized into two domains:

1. **Deterministic DSP & Audio Engineering**:
   * **Loudness & Dynamics**: Integrated LUFS, Short-Term LUFS, True Peak (dBFS), Dynamic Range (DR score / crest factor).
   * **Spectral & Spatial**: Frequency distribution (energy across sub-bass, bass, mids, presence, brilliance), stereo width, phase correlation index (-1 to +1).
   * **Rhythm & Tuning**: Global BPM, beat grid, micro-timing deviation, musical key and scale detection, concert pitch reference (e.g. 440 Hz vs 432 Hz).

2. **Deep Learning AI Models (July 2026+ Tier)**:
   * **Source Separation**: 6-stem isolation (BS-RoFormer: Vocals, Drums, Bass, Guitar, Piano, Other).
   * **Lead Sheet & Transcription**: Audio-to-MIDI polyphonic transcription and chord progression modeling (SheetSage2 / Basic Pitch).
   * **Structural Segmentation**: Macro-structure boundaries (Intro, Verse, Chorus, Bridge, Outro, Solo) via MERT-v2 / Lightcut.
   * **Full-Song Embeddings**: MERT-v2 full-track representation vectors for similarity and acoustic categorization.
   * **Intelligent Mix Critique**: Audio-LLM (Qwen2-Audio-MixAssist) generating qualitative mixing advice, highlighting frequency masking or vocal sibilance.

### FR-3: Zero-Rebuild Plugin Architecture
* **Standard Plugin Interface**: All analyzers must inherit from a unified base class (`BaseAnalyzer`) defining input specifications, execution requirements, and normalized output schemas.
* **Auto-Discovery**: The application must automatically discover and register any plugin file placed in a designated `plugins/` directory on boot or reload.
* **Dependency Chaining**: Plugins must be able to declare dependencies (e.g., a *Bass Guitar Transcriber* plugin declares that it requires the output of the *Stem Separator: Bass* plugin).
* **Hot Deployment Without Container Rebuilds**: The system must support running newly added plugins without triggering local Docker builds or image pushes over residential uplinks.

### FR-4: Client Interfaces
* **Command-Line Interface (CLI)**: Fast, scriptable terminal utility for single files or batch folder processing (`python analyze.py track.wav --output report.json`).
* **Web Dashboard**: Interactive, local or hosted browser interface featuring:
  * Audio player with interactive waveform and chord/section timeline.
  * Multi-track stem player with individual solo and mute buttons.
  * Audio engineering meters (LUFS gauges, stereo field goniometer, frequency spectrum).
  * Direct downloads for separated stems (`.wav`) and generated MIDI files (`.mid`).

---

## 4. Non-Functional Requirements

* **Idle Cost**: Must approach $0/month when the system is not actively analyzing tracks.
* **Inference Speed**: A standard 3.5-minute track must complete full analysis (DSP + Stems + Chords + AI critique) in under 90 seconds on a cloud GPU.
* **Extensibility**: Adding a new analyzer must require writing only one isolated Python file without modifying core orchestrator code.
* **Resilience**: A failure in one experimental plugin must not crash the entire pipeline; remaining analyzers must still complete and deliver their results.
* **Reproducibility**: Analysis outputs must be deterministic or seeded for consistent results.

---

## 5. Architectural Proposals

Below are three distinct architectures designed to meet the functional requirements, each trading off latency, cost, and developer workflow.

---

### Architecture Option A: Pure Serverless with Dynamic Volume Mount (Zero Idle Cost / Zero Rebuilds)

#### Overview
A client-serverless model where the cloud execution container is a generic, immutable base worker, while all plugins, model weights, and custom code live on a persistent RunPod Network Volume.

#### Component Breakdown
* **Client**: Lightweight CLI or local web app running on your machine.
* **Compute**: RunPod Serverless GPU Worker (RTX 4090 or L40S).
* **Storage**: RunPod 200 GB Persistent Network Volume (`EUR-IS-1`).
* **Workflow**:
  1. The generic serverless container mounts the 200 GB volume at `/runpod-volume`.
  2. The worker imports plugins dynamically from `/runpod-volume/plugins/` and reads cached model weights from `/runpod-volume/models/`.
  3. The client submits an audio file to the serverless API.
  4. RunPod wakes up a worker, executes all active plugins against the audio, deposits generated stems/MIDI to the volume, and returns a consolidated JSON response to the client.
  5. The serverless worker turns off immediately after the request.

#### How Plugins Are Added Without Docker Rebuilds
* You place a new Python script (`new_plugin.py`) into the network volume via SSH, SFTP, or an automated sync script.
* The next serverless execution automatically discovers and runs the new plugin.
* **Docker container is never rebuilt.**

#### Trade-offs
* **Pros**:
  * Absolutely $0 compute cost when not running.
  * Zero Docker rebuilds for new plugins or model updates.
  * Auto-scales if you process multiple tracks concurrently.
* **Cons**:
  * Cold start latency: 15–30 seconds to spin up an idle worker and attach the network volume.
  * Network Volume must reside in the same data center region as the serverless worker pool.

---

### Architecture Option B: Hybrid Edge-Cloud Split (Instant Local DSP + On-Demand GPU AI)

#### Overview
Splits execution into two clear tiers: instantaneous, zero-cost DSP and feature extraction run locally on your computer's CPU; heavy neural networks (stems, audio LLM, transcription) are dispatched to RunPod Serverless only when requested.

#### Component Breakdown
* **Local Edge Tier (Your Machine)**:
  * Runs Python DSP tools (`librosa`, `scipy`, `soundfile`, `aubio`).
  * Instantaneous (< 2 seconds) analysis of BPM, key, LUFS loudness, phase correlation, frequency spectrum, and clipping.
  * Manages the local UI and plugin registry for local tools.
* **Cloud GPU Tier (RunPod Serverless)**:
  * Triggered via selective checkboxes in the client UI (e.g. `[x] Run 6-Stem Isolation`, `[x] AI Mix Critique`).
  * Runs only the heavy models requested, reducing GPU runtime and cost.
  * Code synced dynamically on startup via GitHub (`git pull` on boot) or volume mount.

#### How Plugins Are Added Without Docker Rebuilds
* **Local Plugins**: Drop a standard Python script into your local `plugins/` directory. It runs locally on your CPU immediately.
* **Cloud AI Plugins**: Commit your plugin to the GitHub repository (`audio-analyzer-suite`). The serverless worker pulls the latest master branch upon starting its job.
* **Docker container is never rebuilt.**

#### Trade-offs
* **Pros**:
  * Instant feedback for 80% of routine audio engineering metrics without spending a cent or waiting on uploads.
  * Granular cost control: you only spend cloud GPU seconds on stems or LLM critiques when you actually need them.
  * Dead-simple plugin development: lightweight DSP plugins can be written and tested locally in minutes.
* **Cons**:
  * Requires Python and basic audio packages installed locally on your client machine.
  * Two runtime targets to manage (`local_cpu` vs `cloud_gpu`).

---

### Architecture Option C: Dedicated Persistent Studio Hub (On-Demand Pod + Web Studio)

#### Overview
A dedicated RunPod container deployed on an on-demand pod (RTX 4090 @ ~$0.34/hr) attached to your 200 GB network volume, running a persistent web server (FastAPI + React/Streamlit). You start the pod when beginning a music session and stop it when finished.

#### Component Breakdown
* **Compute**: On-demand RunPod GPU Pod (stopped when inactive).
* **Storage**: 200 GB Persistent Network Volume mounted to `/workspace`.
* **Application**: Full web-based DAW/analyzer hosted inside the pod, accessed through browser.
* **Workflow**:
  1. You turn on the pod via `runpodctl start pod` (or a single desktop launch script).
  2. All models are already loaded in GPU VRAM (no cold starts).
  3. You open `https://<pod-id>-8000.proxy.runpod.net` in your browser.
  4. Drag and drop entire albums or folders. Analysis is instant, stems are stored permanently on the 200 GB volume, and you can play/solo stems in the browser.
  5. You stop the pod when done.

#### How Plugins Are Added Without Docker Rebuilds
* The pod has an active shell, JupyterLab, and file tree.
* You can write, edit, or `git pull` plugins directly in the pod's `/workspace/plugins/` directory.
* Changes take effect immediately upon saving the file.
* **Docker container is never rebuilt.**

#### Trade-offs
* **Pros**:
  * Zero cold starts during an active session; back-to-back track analysis is blazing fast.
  * Ideal for batch processing entire discographies or sample libraries.
  * Full audio playback and stem mixing right in the browser without downloading gigabytes of stems to your laptop.
* **Cons**:
  * Costs ~$0.34 per hour while the pod is powered on.
  * Requires remembering to turn the pod off after your session.

---

## 6. Architecture Comparison Matrix

| Evaluation Dimension | Architecture A: Pure Serverless | Architecture B: Hybrid Edge-Cloud | Architecture C: Persistent Studio Hub |
| :--- | :--- | :--- | :--- |
| **Idle Monthly Cost** | **$0.00** | **$0.00** | **$0.00** (when stopped; volume only) |
| **Active Run Cost** | ~$0.01 – $0.03 per song | ~$0.005 – $0.02 per song | ~$0.34 / hour flat |
| **Cold Start Latency** | 20 – 40 seconds | Instant local; 20s for cloud AI | **0 seconds** (while pod is on) |
| **DSP Analysis Speed** | 20 – 30s | **< 2 seconds** | < 2 seconds |
| **Batch Processing** | High concurrency (parallel) | Sequential / on-demand | Excellent queue processing |
| **Local System Overhead**| None (runs anywhere) | Low (CPU DSP only) | None (runs in browser) |
| **Ease of Adding Plugins**| High (drop into volume) | **Highest** (local or git sync) | High (edit live in workspace) |
| **Docker Rebuilds Needed**| **No** (volume-mounted) | **No** (git pull / volume) | **No** (live workspace) |

---

## 7. Technical Specification: The Plugin Engine

To guarantee expandability without code rewrites, all architectures will implement the following base plugin contract:

```python
# core/plugin_interface.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseAnalyzer(ABC):
    name: str = "base_analyzer"
    version: str = "1.0.0"
    description: str = "Base analyzer template"
    execution_target: str = "local_cpu"  # or "cloud_gpu"
    dependencies: List[str] = []         # e.g., ["stem_separator:vocals"]

    @abstractmethod
    def run(self, audio_path: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes analysis on the audio file.
        :param audio_path: Absolute path to the audio file (.wav/.mp3)
        :param context: Dictionary containing outputs from dependency analyzers
        :return: Standardized dictionary of analysis results
        """
        pass
```

### Auto-Discovery Mechanism
```python
# core/registry.py
import importlib.util
import os
from typing import Dict, Type
from core.plugin_interface import BaseAnalyzer

class PluginRegistry:
    def __init__(self, plugin_dir: str):
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, BaseAnalyzer] = {}

    def discover_and_load(self):
        for file in os.listdir(self.plugin_dir):
            if file.endswith(".py") and not file.startswith("__"):
                plugin_path = os.path.join(self.plugin_dir, file)
                module_name = file[:-3]
                spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for item_name in dir(module):
                    item = getattr(module, item_name)
                    if isinstance(item, type) and issubclass(item, BaseAnalyzer) and item is not BaseAnalyzer:
                        instance = item()
                        self.plugins[instance.name] = instance
        return self.plugins
```

---

## 8. Phased Implementation Roadmap

* **Phase 1: Plugin Core & Local Baseline**
  * Implement `BaseAnalyzer` interface and dynamic `PluginRegistry`.
  * Create baseline local DSP plugins: Loudness (LUFS/True Peak), Tempo/BPM, Musical Key, and Spectral Distribution.
  * Verify local zero-dependency discovery.
* **Phase 2: Cloud Runner & AI Plugin Adapters**
  * Create generic RunPod worker base image with PyTorch, CUDA, and audio dependencies.
  * Configure dynamic code loading via Network Volume mount and GitHub sync.
  * Wrap heavy AI models as modular plugins: BS-RoFormer (6-stem), SheetSage2 (lead sheet to MIDI), and MERT-v2 (structure).
* **Phase 3: Client Experience & Reporting**
  * Build the web visualizer (interactive waveforms, stem solo/mute player, chord timeline).
  * Build the CLI exporter (`--json`, `--markdown`, `--midi`).
* **Phase 4: Ecosystem & Extensibility Verification**
  * Document plugin creation guide (`docs/PLUGINS.md`).
  * Drop in a new community model to verify end-to-end zero-rebuild hot reload.

---

## 9. Decision Checklist for the Driver (User)

Before implementation starts, the user should decide on:
1. **Primary Architectural Route**:
   * **Option A**: Pure Serverless (Hands-off, $0 idle, cold-start delay).
   * **Option B**: Hybrid Edge-Cloud (Instant local DSP, cloud GPU only for stems/AI).
   * **Option C**: Persistent Studio Hub (On-demand web DAW pod, zero cold starts, $0.34/hr when on).
2. **First Model Priority**: Which heavy model do you want operational first? (Stem separation, SheetSage2 chord transcription, or Mix critique).
