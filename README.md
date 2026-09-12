# 🎵 AI Music & Audio Analysis Suite for RunPod Serverless

A complete serverless AI audio pipeline that lets you analyze local `.mp3`, `.wav`, `.flac`, and `.ogg` files directly from your computer using on-demand RunPod GPU infrastructure.

Runs on **RunPod Serverless**—paying only for the exact seconds of compute used, automatically scaling to **$0/hr** when idle.

---

## 🚀 Features

* **Tonality & Key Estimation**: Correlates chroma pitch class profiles against Krumhansl-Schmuckler harmonic templates for all 24 major & minor keys.
* **Tempo & Beat Tracking**: Precise BPM detection and beat onset grid alignment.
* **Harmonic Chord Progression**: Time-aligned chord changes (`Am`, `F`, `C`, `G`, etc.).
* **Structural Section Segmentation**: Automatic detection and labeling of song sections (`Intro`, `Verse`, `Chorus`, `Bridge/Breakdown`, `Outro`).
* **Audio Engineering & Mastering Metrics**: RMS energy (dBFS), peak loudness, dynamic range classification, spectral brightness (centroid), and rolloff.
* **Direct Local Uploads**: Zero cloud storage or S3 buckets needed—client encodes local audio into Base64 and transmits it directly to the GPU in RAM.
* **Multiple Client Interfaces**: Includes both a rich terminal CLI (`client/analyze.py`) and a zero-dependency visual web dashboard (`client/web_app.py`).

---

## 🏗️ Architecture

```
[ Local Computer ]
├── client/analyze.py     (Terminal CLI)   ──( Base64 Audio Payload )──┐
└── client/web_app.py     (Web Dashboard) ──┘                          │
                                                                       ▼
                                                          [ RunPod Serverless GPU ]
                                                          ├── Decodes in RAM
                                                          ├── Extracts Features
                                                          └── Computes Analysis
                                                                       │
[ Local Results Display ] ◀────────( Returns Structured JSON )─────────┘
```

---

## 📦 Project Structure

```
audio-analyzer-suite/
├── server/
│   ├── handler.py           # RunPod Serverless worker handler
│   ├── Dockerfile           # GPU container with PyTorch, librosa & soundfile
│   └── requirements.txt     # Python dependencies for worker
├── client/
│   ├── analyze.py           # Local CLI script to analyze tracks
│   ├── web_app.py           # Local browser dashboard (zero-dependency)
│   └── requirements.txt     # Client dependencies (runpod, rich)
├── .gitignore
└── README.md
```

---

## 🛠️ Step 1: Deploy to RunPod Serverless (One-Time Setup)

### Option A: Via RunPod Web Console
1. Log in to [RunPod Serverless Console](https://www.runpod.io/console/serverless).
2. Click **New Endpoint**.
3. Set your container image (or build and push the `server/Dockerfile` to Docker Hub):
   ```
   runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04
   ```
4. Select GPU type: **RTX 4090**, **A100**, or **L40S**.
5. Set **Max Workers** to `3` and **Idle Timeout** to `5` seconds.
6. Click **Deploy** and copy your **Endpoint ID** (e.g. `abc123xyz`).

---

## 💻 Step 2: Running from Your Local Computer

### 1. Install Client Dependencies
```bash
cd client
pip install -r requirements.txt
```

### 2. Configure Your RunPod Credentials
```bash
export RUNPOD_API_KEY="your-runpod-api-key"
export RUNPOD_ENDPOINT_ID="your-endpoint-id"
```
*(If you already ran `runpodctl doctor`, your API key is automatically detected from `~/.runpod/config.toml`)*.

---

## 🖥️ Usage

### Command Line Interface (`client/analyze.py`)

Analyze any local audio file:
```bash
python3 client/analyze.py ~/Music/my_track.mp3
```

Save the detailed report to a JSON file:
```bash
python3 client/analyze.py ~/Music/my_track.wav --output analysis.json
```

### Visual Web Dashboard (`client/web_app.py`)

Launch the local web dashboard:
```bash
python3 client/web_app.py --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your browser:
* Drag and drop any `.mp3` or `.wav` file.
* View interactive Key/BPM meters, visual section timelines, chord progression pills, and mastering dynamics.

---

## 📊 Sample Output Schema

```json
{
  "status": "success",
  "metadata": {
    "duration_seconds": 214.5,
    "sample_rate": 22050,
    "total_samples": 4729725
  },
  "musical_analysis": {
    "key": "G Minor",
    "key_confidence": 0.84,
    "bpm": 126.0,
    "detected_beats_count": 448,
    "chord_progression_summary": ["Gm", "Eb", "Bb", "F"],
    "chord_timeline": [
      {"chord": "Gm", "start_time": 0.0, "end_time": 4.2},
      {"chord": "Eb", "start_time": 4.2, "end_time": 8.1}
    ]
  },
  "structure_analysis": {
    "total_sections": 5,
    "sections": [
      {"section": "Intro", "start_time": 0.0, "end_time": 15.0, "duration": 15.0, "relative_energy": "Low"},
      {"section": "Verse", "start_time": 15.0, "end_time": 45.5, "duration": 30.5, "relative_energy": "Low"},
      {"section": "Chorus / Drop", "start_time": 45.5, "end_time": 76.0, "duration": 30.5, "relative_energy": "High"}
    ]
  },
  "audio_engineering": {
    "average_rms_dbfs": -13.8,
    "peak_dbfs": -0.2,
    "dynamic_range_db": 13.6,
    "dynamics_profile": "Balanced Modern Commercial Master",
    "spectral_brightness_hz": 2650.4,
    "spectral_rolloff_hz": 5420.1
  }
}
```

---

## 📄 License

MIT License — free for personal and commercial audio production workflows.
