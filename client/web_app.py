#!/usr/bin/env python3
"""
Audio Analyzer Web Dashboard
A zero-dependency local web interface for uploading local MP3/WAV tracks and visualizing analysis results.
"""

import os
import sys
import json
import base64
import http.server
import socketserver
import argparse
from pathlib import Path

try:
    import runpod
except ImportError:
    runpod = None

def get_default_api_key():
    if os.environ.get("RUNPOD_API_KEY"):
        return os.environ["RUNPOD_API_KEY"]
    config = Path.home() / ".runpod" / "config.toml"
    if config.exists():
        for line in config.read_text().splitlines():
            if "apikey" in line:
                return line.split("=")[1].strip().strip("'\"")
    return ""

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Audio Analyzer Suite</title>
    <style>
        :root {
            --bg: #0d1117;
            --surface: #161b22;
            --border: #30363d;
            --text: #f0f6fc;
            --text-dim: #8b949e;
            --accent: #58a6ff;
            --accent-green: #3fb950;
            --accent-purple: #bc8cff;
            --accent-orange: #d29922;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
        body { background: var(--bg); color: var(--text); padding: 2rem; }
        .container { max-width: 900px; margin: 0 auto; }
        header { text-align: center; margin-bottom: 2rem; }
        h1 { font-size: 2.2rem; margin-bottom: 0.5rem; background: linear-gradient(90deg, #58a6ff, #bc8cff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        p.subtitle { color: var(--text-dim); }
        .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        .settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
        label { display: block; font-size: 0.85rem; font-weight: 600; color: var(--text-dim); margin-bottom: 0.3rem; }
        input[type="text"], input[type="password"] { width: 100%; padding: 0.6rem 0.8rem; background: #010409; border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 0.9rem; }
        .dropzone { border: 2px dashed var(--border); border-radius: 8px; padding: 2.5rem; text-align: center; cursor: pointer; transition: 0.2s border-color; background: #010409; }
        .dropzone:hover { border-color: var(--accent); }
        .btn { display: inline-block; width: 100%; padding: 0.8rem; background: #238636; color: white; border: none; border-radius: 6px; font-weight: 600; font-size: 1rem; cursor: pointer; margin-top: 1rem; transition: background 0.2s; }
        .btn:hover { background: #2ea043; }
        .btn:disabled { background: #30363d; cursor: not-allowed; }
        .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-top: 1.5rem; }
        .stat-card { background: #010409; border: 1px solid var(--border); border-radius: 8px; padding: 1rem; text-align: center; }
        .stat-val { font-size: 1.6rem; font-weight: bold; color: var(--accent); margin-top: 0.3rem; }
        .stat-label { font-size: 0.75rem; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.5px; }
        .timeline { display: flex; height: 36px; border-radius: 6px; overflow: hidden; margin-top: 1rem; border: 1px solid var(--border); }
        .timeline-seg { display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: bold; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.6); }
        .chord-pill { display: inline-block; background: rgba(188, 140, 255, 0.15); border: 1px solid var(--accent-purple); color: var(--accent-purple); padding: 0.3rem 0.6rem; border-radius: 20px; font-size: 0.85rem; font-weight: 600; margin: 0.2rem; }
        #loading { display: none; text-align: center; margin: 1.5rem 0; font-weight: 600; color: var(--accent); }
        #results { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>AI Music & Audio Analyzer</h1>
            <p class="subtitle">RunPod Serverless GPU Pipeline • Key, BPM, Chords, Structure & Mastering Dynamics</p>
        </header>

        <div class="card">
            <div class="settings-grid">
                <div>
                    <label>RunPod Endpoint ID</label>
                    <input type="text" id="endpointId" placeholder="e.g. 5wykflm7ef" value="">
                </div>
                <div>
                    <label>RunPod API Key</label>
                    <input type="password" id="apiKey" placeholder="rpa_..." value="">
                </div>
            </div>

            <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
                <svg width="40" height="40" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="color: var(--text-dim); margin-bottom: 0.5rem;"><path d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"></path></svg>
                <p id="fileLabel">Click or drop audio file here (.mp3, .wav, .flac, .ogg)</p>
                <input type="file" id="fileInput" accept="audio/*" style="display:none" onchange="fileSelected(this.files)">
            </div>

            <button class="btn" id="analyzeBtn" onclick="runAnalysis()" disabled>Analyze Track</button>
            <div id="loading">⚡ Sending to RunPod Serverless GPU & analyzing track...</div>
        </div>

        <div class="card" id="results">
            <h2 style="font-size: 1.3rem; margin-bottom: 1rem;" id="trackTitle">Analysis Results</h2>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Detected Key</div>
                    <div class="stat-val" id="resKey" style="color: var(--accent-green)">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Tempo (BPM)</div>
                    <div class="stat-val" id="resBpm" style="color: var(--accent-orange)">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Loudness (RMS)</div>
                    <div class="stat-val" id="resRms">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Duration</div>
                    <div class="stat-val" id="resDuration">-</div>
                </div>
            </div>

            <h3 style="margin-top: 1.5rem; margin-bottom: 0.5rem; font-size: 1rem; color: var(--text-dim);">Song Structure Timeline</h3>
            <div class="timeline" id="resTimeline"></div>

            <h3 style="margin-top: 1.5rem; margin-bottom: 0.5rem; font-size: 1rem; color: var(--text-dim);">Harmonic Chord Progression</h3>
            <div id="resChords"></div>

            <h3 style="margin-top: 1.5rem; margin-bottom: 0.5rem; font-size: 1rem; color: var(--text-dim);">Audio Engineering & Profile</h3>
            <p id="resDynamics" style="font-weight: 600; color: var(--text); margin-top: 0.3rem;"></p>
        </div>
    </div>

    <script>
        let selectedFile = null;
        const defaultKey = "__DEFAULT_KEY__";
        const defaultEndpoint = "__DEFAULT_ENDPOINT__";
        if (defaultKey) document.getElementById('apiKey').value = defaultKey;
        if (defaultEndpoint) document.getElementById('endpointId').value = defaultEndpoint;

        function fileSelected(files) {
            if (files && files[0]) {
                selectedFile = files[0];
                document.getElementById('fileLabel').innerText = `Selected: ${selectedFile.name} (${(selectedFile.size / 1024 / 1024).toFixed(2)} MB)`;
                document.getElementById('analyzeBtn').disabled = false;
            }
        }

        async function runAnalysis() {
            if (!selectedFile) return;
            const endpointId = document.getElementById('endpointId').value.trim();
            const apiKey = document.getElementById('apiKey').value.trim();

            if (!endpointId) return alert('Please enter your RunPod Endpoint ID');
            if (!apiKey) return alert('Please enter your RunPod API Key');

            document.getElementById('analyzeBtn').disabled = true;
            document.getElementById('loading').style.display = 'block';
            document.getElementById('results').style.display = 'none';

            // Convert file to Base64
            const reader = new FileReader();
            reader.readAsDataURL(selectedFile);
            reader.onload = async function () {
                const base64Data = reader.result.split(',')[1];
                try {
                    const resp = await fetch('/api/analyze', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            endpoint_id: endpointId,
                            api_key: apiKey,
                            audio_base64: base64Data,
                            filename: selectedFile.name
                        })
                    });
                    const res = await resp.json();
                    if (res.error) throw new Error(res.error);
                    displayResults(res);
                } catch (err) {
                    alert('Analysis Error: ' + err.message);
                } finally {
                    document.getElementById('analyzeBtn').disabled = false;
                    document.getElementById('loading').style.display = 'none';
                }
            };
        }

        function displayResults(data) {
            document.getElementById('results').style.display = 'block';
            document.getElementById('trackTitle').innerText = data.filename || 'Analysis Results';
            
            const music = data.musical_analysis || {};
            const meta = data.metadata || {};
            const eng = data.audio_engineering || {};
            const struct = data.structure_analysis || {};

            document.getElementById('resKey').innerText = music.key || 'N/A';
            document.getElementById('resBpm').innerText = music.bpm || 'N/A';
            document.getElementById('resRms').innerText = (eng.average_rms_dbfs || 0) + ' dB';
            document.getElementById('resDuration').innerText = (meta.duration_seconds || 0) + 's';

            // Render Chords
            const chordsDiv = document.getElementById('resChords');
            chordsDiv.innerHTML = '';
            (music.chord_progression_summary || []).slice(0, 16).forEach(c => {
                const pill = document.createElement('span');
                pill.className = 'chord-pill';
                pill.innerText = c;
                chordsDiv.appendChild(pill);
            });

            // Render Timeline
            const timeline = document.getElementById('resTimeline');
            timeline.innerHTML = '';
            const colors = ['#238636', '#1f6feb', '#8957e5', '#d29922', '#da3633'];
            const totalDur = meta.duration_seconds || 1;
            (struct.sections || []).forEach((sec, idx) => {
                const seg = document.createElement('div');
                seg.className = 'timeline-seg';
                const pct = ((sec.duration || 1) / totalDur) * 100;
                seg.style.width = pct + '%';
                seg.style.backgroundColor = colors[idx % colors.length];
                seg.innerText = sec.section;
                seg.title = `${sec.section}: ${sec.start_time}s - ${sec.end_time}s`;
                timeline.appendChild(seg);
            });

            document.getElementById('resDynamics').innerText = `${eng.dynamics_profile || 'Balanced'} • Dynamic Range: ${eng.dynamic_range_db || 0} dB • Brightness: ${eng.spectral_brightness_hz || 0} Hz`;
        }
    </script>
</body>
</html>
"""

class AnalyzerServer(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            rendered = HTML_PAGE.replace("__DEFAULT_KEY__", get_default_api_key())
            rendered = rendered.replace("__DEFAULT_ENDPOINT__", os.environ.get("RUNPOD_ENDPOINT_ID", ""))
            self.wfile.write(rendered.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/analyze":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)

            endpoint_id = data.get("endpoint_id")
            api_key = data.get("api_key")
            audio_base64 = data.get("audio_base64")
            filename = data.get("filename", "audio.mp3")

            if not runpod:
                self.send_json({"error": "runpod python package not installed on local host"})
                return

            try:
                runpod.api_key = api_key
                endpoint = runpod.Endpoint(endpoint_id)
                response = endpoint.run_sync({
                    "audio_base64": audio_base64,
                    "filename": filename
                })
                output = response.get("output", response)
                output["filename"] = filename
                self.send_json(output)
            except Exception as e:
                self.send_json({"error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, payload):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

def main():
    parser = argparse.ArgumentParser(description="Launch local Web Dashboard for Audio Analyzer")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Web server port (default 8000)")
    args = parser.parse_args()

    print(f"Starting Audio Analyzer Web Dashboard on http://localhost:{args.port}")
    print("Press Ctrl+C to stop.")
    with socketserver.TCPServer(("", args.port), AnalyzerServer) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    main()
