import io
import base64
import requests
import numpy as np
import soundfile as sf
import librosa
import runpod

# Krumhansl-Schmuckler key profiles for key estimation
PITCH_CLASSES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

def estimate_key(chroma_mean):
    """Correlate mean chroma with Krumhansl-Schmuckler key profiles."""
    chroma_norm = chroma_mean / (np.linalg.norm(chroma_mean) + 1e-8)
    best_corr = -1
    best_key = "C major"

    for i in range(12):
        # Major
        rot_major = np.roll(MAJOR_PROFILE, i)
        rot_major_norm = rot_major / np.linalg.norm(rot_major)
        corr_major = np.corrcoef(chroma_norm, rot_major_norm)[0, 1]
        if corr_major > best_corr:
            best_corr = corr_major
            best_key = f"{PITCH_CLASSES[i]} Major"

        # Minor
        rot_minor = np.roll(MINOR_PROFILE, i)
        rot_minor_norm = rot_minor / np.linalg.norm(rot_minor)
        corr_minor = np.corrcoef(chroma_norm, rot_minor_norm)[0, 1]
        if corr_minor > best_corr:
            best_corr = corr_minor
            best_key = f"{PITCH_CLASSES[i]} Minor"

    return best_key, round(float(max(0, best_corr)), 3)

def detect_chords(chroma, sample_rate, hop_length=512, segment_duration=2.0):
    """Estimate chord sequence across time intervals."""
    frames_per_sec = sample_rate / hop_length
    frames_per_seg = max(1, int(frames_per_sec * segment_duration))
    total_frames = chroma.shape[1]

    chords = []
    # Simplified chord templates: Major [0, 4, 7] and Minor [0, 3, 7]
    triad_templates = {}
    for i, root in enumerate(PITCH_CLASSES):
        # Major triad
        maj_vec = np.zeros(12)
        maj_vec[[i, (i + 4) % 12, (i + 7) % 12]] = 1.0
        triad_templates[root] = maj_vec

        # Minor triad
        min_vec = np.zeros(12)
        min_vec[[i, (i + 3) % 12, (i + 7) % 12]] = 1.0
        triad_templates[f"{root}m"] = min_vec

    for start_f in range(0, total_frames, frames_per_seg):
        end_f = min(start_f + frames_per_seg, total_frames)
        seg_chroma = np.mean(chroma[:, start_f:end_f], axis=1)
        seg_norm = seg_chroma / (np.linalg.norm(seg_chroma) + 1e-8)

        best_score = -1
        best_chord = "N/C"

        for chord_name, template in triad_templates.items():
            t_norm = template / np.linalg.norm(template)
            score = np.dot(seg_norm, t_norm)
            if score > best_score:
                best_score = score
                best_chord = chord_name

        start_time = round(start_f / frames_per_sec, 2)
        end_time = round(end_f / frames_per_sec, 2)

        # Merge contiguous identical chords
        if chords and chords[-1]["chord"] == best_chord:
            chords[-1]["end_time"] = end_time
        else:
            chords.append({
                "chord": best_chord,
                "start_time": start_time,
                "end_time": end_time
            })

    return chords

def analyze_structure(y, sr, duration):
    """Segment song into structural sections based on spectral novelty & energy."""
    try:
        hop_length = 1024
        # Feature matrix of MFCCs + Chroma
        mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop_length, n_mfcc=13)
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        
        # Agglomerative clustering for segmentation boundaries
        n_segments = min(8, max(3, int(duration / 30)))  # ~30s per section
        boundaries = librosa.segment.agglomerative(mfcc, k=n_segments)
        bound_times = librosa.frames_to_time(boundaries, sr=sr, hop_length=hop_length)
        bound_times = np.concatenate(([0.0], bound_times, [duration]))
        bound_times = np.unique(np.round(bound_times, 2))

        # Classify sections based on position and relative energy
        mean_rms = np.mean(rms)
        sections = []
        frames_per_sec = sr / hop_length

        for i in range(len(bound_times) - 1):
            t_start = bound_times[i]
            t_end = bound_times[i + 1]
            seg_len = t_end - t_start

            f_start = int(t_start * frames_per_sec)
            f_end = int(t_end * frames_per_sec)
            seg_energy = np.mean(rms[f_start:f_end]) if f_end > f_start else mean_rms

            # Heuristic labeling based on energy and time position
            pos_ratio = t_start / max(1.0, duration)
            if pos_ratio < 0.12:
                label = "Intro"
            elif pos_ratio > 0.88:
                label = "Outro"
            elif seg_energy > mean_rms * 1.15:
                label = "Chorus / Drop"
            elif seg_energy < mean_rms * 0.85:
                label = "Bridge / Breakdown"
            else:
                label = "Verse"

            sections.append({
                "section": label,
                "start_time": float(t_start),
                "end_time": float(t_end),
                "duration": round(float(seg_len), 2),
                "relative_energy": "High" if seg_energy > mean_rms else "Low"
            })

        return sections
    except Exception as e:
        return [{"section": "Full Track", "start_time": 0.0, "end_time": round(duration, 2), "error": str(e)}]

def analyze_audio_pipeline(audio_bytes):
    """Complete audio analysis suite."""
    # 1. Decode audio from bytes in memory
    with io.BytesIO(audio_bytes) as bio:
        y, sr = librosa.load(bio, sr=22050, mono=True)

    duration = float(librosa.get_duration(y=y, sr=sr))

    # 2. Rhythm & Tempo Analysis
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm = round(float(np.atleast_1d(tempo)[0]), 1)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    downbeats_preview = [round(t, 3) for t in beat_times[:16]]  # First 16 beats

    # 3. Tonality & Chords
    chroma_cens = librosa.feature.chroma_cens(y=y, sr=sr)
    chroma_mean = np.mean(chroma_cens, axis=1)
    estimated_key, key_confidence = estimate_key(chroma_mean)
    chord_sequence = detect_chords(chroma_cens, sample_rate=sr)

    # 4. Structure & Section Segmentation
    sections = analyze_structure(y, sr, duration)

    # 5. Audio Engineering & Spectral Metrics
    rms = librosa.feature.rms(y=y)[0]
    rms_db = round(float(librosa.amplitude_to_db(rms).mean()), 2)
    peak_db = round(float(librosa.amplitude_to_db(np.max(np.abs(y)))), 2)

    spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    brightness_hz = round(float(np.mean(spectral_centroids)), 1)

    spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
    rolloff_hz = round(float(np.mean(spectral_rolloff)), 1)

    zero_crossings = librosa.feature.zero_crossing_rate(y)[0]
    noisiness = round(float(np.mean(zero_crossings)), 4)

    # Dynamics classification
    dynamic_range_db = round(abs(peak_db - rms_db), 2)
    if dynamic_range_db > 18:
        dynamics_label = "Wide Dynamic Range (Uncompressed / Acoustic)"
    elif dynamic_range_db < 9:
        dynamics_label = "Heavily Compressed / Limiter Driven"
    else:
        dynamics_label = "Balanced Modern Commercial Master"

    return {
        "status": "success",
        "metadata": {
            "duration_seconds": round(duration, 2),
            "sample_rate": sr,
            "total_samples": len(y)
        },
        "musical_analysis": {
            "key": estimated_key,
            "key_confidence": key_confidence,
            "bpm": bpm,
            "detected_beats_count": len(beat_times),
            "beat_grid_preview_sec": downbeats_preview,
            "chord_progression_summary": [c["chord"] for c in chord_sequence[:12]],
            "chord_timeline": chord_sequence
        },
        "structure_analysis": {
            "total_sections": len(sections),
            "sections": sections
        },
        "audio_engineering": {
            "average_rms_dbfs": rms_db,
            "peak_dbfs": peak_db,
            "dynamic_range_db": dynamic_range_db,
            "dynamics_profile": dynamics_label,
            "spectral_brightness_hz": brightness_hz,
            "spectral_rolloff_hz": rolloff_hz,
            "percussiveness_index": noisiness
        }
    }

def handler(event):
    """RunPod serverless request handler."""
    job_input = event.get("input", {})

    if not job_input:
        return {"error": "Empty input payload. Provide 'audio_base64' or 'audio_url'."}

    try:
        # Load audio from Base64 or URL
        if "audio_base64" in job_input:
            b64_data = job_input["audio_base64"]
            # Handle potential data URL header (e.g. data:audio/mp3;base64,...)
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            audio_bytes = base64.b64decode(b64_data)
        elif "audio_url" in job_input:
            resp = requests.get(job_input["audio_url"], timeout=30)
            resp.raise_for_status()
            audio_bytes = resp.content
        else:
            return {"error": "Missing audio. Please supply 'audio_base64' string or 'audio_url' string."}

        # Run analysis pipeline
        results = analyze_audio_pipeline(audio_bytes)
        if "filename" in job_input:
            results["filename"] = job_input["filename"]

        return results

    except Exception as err:
        return {
            "status": "error",
            "error_type": type(err).__name__,
            "message": str(err)
        }

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
