"""Compile and import smoke checks for the client and the RunPod handler."""

import base64
import compileall
import importlib.util
import io
import math
import struct
import sys
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CompileSmokeTest(unittest.TestCase):
    def test_client_and_server_compile(self):
        self.assertTrue(compileall.compile_dir(str(ROOT / "client"), quiet=1))
        self.assertTrue(compileall.compile_dir(str(ROOT / "server"), quiet=1))


class ClientSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyze = load_module("analyze", ROOT / "client" / "analyze.py")
        cls.web_app = load_module("web_app", ROOT / "client" / "web_app.py")

    def test_format_seconds(self):
        self.assertEqual(self.analyze.format_seconds(90.5), "1m 30.5s")

    def test_api_key_comes_from_the_environment(self):
        previous = self.analyze.os.environ.get("RUNPOD_API_KEY")
        self.analyze.os.environ["RUNPOD_API_KEY"] = "rpa_smoke"
        try:
            self.assertEqual(self.analyze.get_api_key(), "rpa_smoke")
            self.assertEqual(self.web_app.get_default_api_key(), "rpa_smoke")
        finally:
            if previous is None:
                self.analyze.os.environ.pop("RUNPOD_API_KEY", None)
            else:
                self.analyze.os.environ["RUNPOD_API_KEY"] = previous

    def test_dashboard_html_is_present(self):
        self.assertIn("AI Music & Audio Analyzer", self.web_app.HTML_PAGE)
        self.assertIn("/api/analyze", self.web_app.HTML_PAGE)


class HandlerSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handler = load_module("handler", ROOT / "server" / "handler.py")

    def test_estimate_key_prefers_its_own_major_profile(self):
        key, confidence = self.handler.estimate_key(self.handler.MAJOR_PROFILE.astype(float))
        self.assertEqual(key, "C Major")
        self.assertGreater(confidence, 0.9)

    def test_detect_chords_names_a_c_major_triad(self):
        import numpy as np

        chroma = np.zeros((12, 8))
        chroma[[0, 4, 7], :] = 1.0
        chords = self.handler.detect_chords(chroma, sample_rate=22050, segment_duration=2.0)
        self.assertEqual(chords[0]["chord"], "C")
        self.assertEqual(chords[0]["start_time"], 0.0)
        self.assertGreater(chords[0]["end_time"], 0.0)

    def test_handler_rejects_an_empty_payload(self):
        result = self.handler.handler({})
        self.assertIn("audio_base64", result["error"])

    def test_handler_rejects_a_payload_without_audio(self):
        result = self.handler.handler({"input": {"filename": "track.wav"}})
        self.assertIn("audio_base64", result["error"])

    def test_handler_analyzes_a_generated_tone(self):
        payload = _sine_wav_base64(seconds=1.0)
        result = self.handler.handler(
            {"input": {"audio_base64": f"data:audio/wav;base64,{payload}", "filename": "tone.wav"}}
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["filename"], "tone.wav")
        self.assertEqual(result["metadata"]["sample_rate"], 22050)
        self.assertGreater(result["metadata"]["duration_seconds"], 0.5)
        self.assertIn("key", result["musical_analysis"])
        self.assertIn("bpm", result["musical_analysis"])
        self.assertGreaterEqual(result["structure_analysis"]["total_sections"], 1)
        self.assertIn("dynamics_profile", result["audio_engineering"])


def _sine_wav_base64(seconds):
    sample_rate = 22050
    frame_count = int(sample_rate * seconds)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            sample = int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate))
            frames.extend(struct.pack("<h", sample))
        wav.writeframes(bytes(frames))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


if __name__ == "__main__":
    unittest.main()
