"""
main.py — Full voice conversation loop

Pipeline:
    Mic -> RealtimeSTT -> speech_normalizer -> agent -> math_renderer -> Deepgram TTS -> Speaker
"""

import os
import warnings
import logging
import tempfile
import wave
import subprocess
import requests
from dotenv import load_dotenv

# Suppress model loading noise
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["CT2_VERBOSE"] = "0"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

from RealtimeSTT import AudioToTextRecorder
from speech_normalizer import normalize
from math_renderer import render_math
from agent import respond, detect_mode

load_dotenv()

# ------------------------------------------------------------------ #
#  Config
# ------------------------------------------------------------------ #

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
TTS_URL = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=24000&channels=1"

# ------------------------------------------------------------------ #
#  State
# ------------------------------------------------------------------ #

history = []
mode = "walkthrough"

# ------------------------------------------------------------------ #
#  TTS — Deepgram Aura
# ------------------------------------------------------------------ #

def speak(text: str):
    """Send text to Deepgram Aura TTS and play audio through speaker."""
    try:
        response = requests.post(
            TTS_URL,
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"text": text},
            timeout=10,
        )
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
            with wave.open(tmp, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(response.content)
        subprocess.run(["afplay", tmp], check=True)
        os.unlink(tmp)
    except Exception as e:
        print(f"  [TTS error: {e}]")


# ------------------------------------------------------------------ #
#  Main transcript callback
# ------------------------------------------------------------------ #

def on_transcript(text: str):
    global history, mode

    text = text.strip()
    if not text:
        return

    print(f"\r> {text}          ")

    # Check for mode switch
    new_mode = detect_mode(text, mode)
    if new_mode != mode:
        mode = new_mode
        print(f"  [switched to {mode} mode]")

    # Normalize math/science notation
    normalized = normalize(text)

    # Get LLM response
    print("  ...", end="", flush=True)
    try:
        response_text, history = respond(normalized, history, mode=mode)
    except Exception as e:
        print(f"\r  [agent error: {e}]")
        return

    # Render math symbols to speakable English
    speakable = render_math(response_text)
    print(f"\r< {speakable}          ")

    # Speak it
    speak(speakable)


# ------------------------------------------------------------------ #
#  Entry point
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    print("lilvro — voice STEM agent")
    print("Mode: walkthrough  |  Say 'quiz mode' / 'teach back' / 'help me' to switch")
    print("Press Ctrl+C to quit\n")

    recorder = AudioToTextRecorder(
        model="tiny.en",
        language="en",
        compute_type="float32",
        silero_sensitivity=0.4,
        post_speech_silence_duration=1.0,
        on_realtime_transcription_stabilized=lambda t: print(f"\r  {t}          ", end="", flush=True),
    )

    try:
        while True:
            recorder.text(on_transcript)
    except KeyboardInterrupt:
        print("\nGoodbye!")
        recorder.stop()
