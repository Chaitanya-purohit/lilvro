"""
main.py — Full voice conversation loop

Pipeline:
    Mic -> RealtimeSTT -> utterance_gate -> speech_normalizer -> agent
      -> math_renderer -> Deepgram TTS -> Speaker

The agent only replies after the student has finished a real utterance —
not on interim text, fillers, or mid-sentence cuts.
"""

import os
import sys
import select
import threading
import warnings
import logging
import tempfile
import wave
import subprocess
import time
import requests
from dotenv import load_dotenv

if os.name == "nt":
    import msvcrt
else:
    import termios
    import tty

# Suppress model loading noise
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["CT2_VERBOSE"] = "0"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

from RealtimeSTT import AudioToTextRecorder
from speech_normalizer import normalize
from math_renderer import render_math
from agent import respond, detect_mode
from utterance_gate import GateDecision, UtteranceGate
from speech_styler import style_speech

load_dotenv()

# ------------------------------------------------------------------ #
#  Config
# ------------------------------------------------------------------ #

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_VOICE = os.getenv("DEEPGRAM_VOICE", "aura-2-thalia-en")
TTS_URL = f"https://api.deepgram.com/v1/speak?model={DEEPGRAM_VOICE}&encoding=linear16&sample_rate=24000&channels=1"

# How long after speech stops before we treat the utterance as finished.
# Kids often pause mid-thought — keep this a bit generous.
POST_SPEECH_SILENCE = 1.4

# ------------------------------------------------------------------ #
#  Feature flags — flip these to enable/disable optional features
# ------------------------------------------------------------------ #

# Noise filter: WebRTC VAD-based noise gate on mic input (0 = off, 1-3 = aggressive)
NOISE_FILTER = True
NOISE_FILTER_LEVEL = 2  # 1 = mild, 2 = moderate, 3 = aggressive

# Echo cancellation: ignore transcripts that arrive while/just after TTS is playing
# so the agent never hears and responds to its own voice.
ECHO_CANCEL = True
ECHO_CANCEL_COOLDOWN = 1.2  # seconds to ignore mic input after TTS finishes

# ------------------------------------------------------------------ #
#  State
# ------------------------------------------------------------------ #

history = []
mode = "walkthrough"
_paused = False
gate = UtteranceGate(
    settle_seconds=0.5,
    min_chars=2,
    min_words=1,
    reject_trailing_incomplete=True,
)
_busy = False  # True while agent/TTS is running — ignore new triggers
_last_spoken_user = ""
_speaking = False      # True while TTS audio is actively playing
_speak_end_time = 0.0  # monotonic timestamp when last TTS finished


# ------------------------------------------------------------------ #
#  Pause / resume — press P in terminal or say "pause" / "resume"
# ------------------------------------------------------------------ #

def _toggle_pause():
    global _paused
    _paused = not _paused
    status = "PAUSED  (press p or say 'resume' to continue)" if _paused else "RESUMED"
    print(f"\n  [{status}]          ")


def _keyboard_watcher():
    """Background thread: press 'p' to toggle pause without killing the process."""
    if os.name == "nt":
        while True:
            ch = msvcrt.getwch()
            if ch.lower() == "p":
                _toggle_pause()
            elif ch == "\x03":
                return

    # Open /dev/tty directly so we don't compete with RealtimeSTT's stdin handling.
    try:
        tty_fd = open("/dev/tty", "rb", buffering=0)
    except OSError:
        return  # no controlling terminal — skip keyboard watcher silently

    old = termios.tcgetattr(tty_fd)
    try:
        tty.setcbreak(tty_fd)
        while True:
            # Non-blocking poll — returns immediately if no key pressed
            ready, _, _ = select.select([tty_fd], [], [], 0.05)
            if ready:
                ch = tty_fd.read(1).decode("utf-8", errors="ignore")
                if ch.lower() == "p":
                    _toggle_pause()
                elif ch == "\x03":
                    raise KeyboardInterrupt
    except Exception:
        pass
    finally:
        termios.tcsetattr(tty_fd, termios.TCSADRAIN, old)
        tty_fd.close()


#  TTS — Deepgram Aura
# ------------------------------------------------------------------ #

_DING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds", "ding.mp3")

def ding():
    """Play a short chime to signal lilvro is about to speak."""
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(_DING, winsound.SND_FILENAME)
    elif sys.platform == "darwin":
        subprocess.run(["afplay", _DING], check=False)
    else:
        subprocess.run(["aplay", _DING], check=False)


def speak(text: str):
    """Send text to Deepgram Aura TTS and play audio through speaker.

    Only called with a complete agent reply — never with partials.
    Sets _speaking while audio plays so the echo-cancel guard can ignore
    any mic transcripts that capture our own output.
    """
    global _speaking, _speak_end_time
    _speaking = True
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
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(tmp, winsound.SND_FILENAME)
        elif sys.platform == "darwin":
            subprocess.run(["afplay", tmp], check=True)
        else:
            subprocess.run(["aplay", tmp], check=True)
    except Exception as e:
        print(f"  [TTS error: {e}]")
    finally:
        if "tmp" in locals():
            try:
                os.unlink(tmp)
            except OSError:
                pass
        _speaking = False
        _speak_end_time = time.monotonic()


# ------------------------------------------------------------------ #
#  Live partials — display only, never reply
# ------------------------------------------------------------------ #

def _is_self_echo() -> bool:
    """Return True if we should ignore this transcript — agent is speaking or just finished."""
    if not ECHO_CANCEL:
        return False
    if _speaking:
        return True
    return time.monotonic() - _speak_end_time < ECHO_CANCEL_COOLDOWN


def on_partial(text: str):
    """Realtime stabilized text: show what we heard, do not answer yet."""
    text = (text or "").strip()
    if not text or _busy or _paused or _is_self_echo():
        return
    gate.feed(text, speech_ended=False, is_interim=True)
    print(f"\r  … {text}          ", end="", flush=True)


# ------------------------------------------------------------------ #
#  Finished utterance callback
# ------------------------------------------------------------------ #

def on_transcript(text: str):
    """Called when STT thinks speech ended. Gate may still WAIT/IGNORE."""
    global history, mode, _busy, _last_spoken_user, _paused

    if _busy or _is_self_echo():
        return

    text = (text or "").strip()
    if not text:
        return

    # Voice-activated pause / resume
    lower = text.lower()
    if any(p in lower for p in ["pause lilvro", "stop listening", "go to sleep"]):
        if not _paused:
            _toggle_pause()
        return
    if any(p in lower for p in ["resume", "wake up", "start listening"]):
        if _paused:
            _toggle_pause()
        return

    if _paused:
        print(f"\r  [paused — press p or say 'resume']          ", end="", flush=True)
        return

    result = gate.feed(text, speech_ended=True, is_interim=False)

    # If still settling / trailing-incomplete, poll briefly then re-check.
    if result.decision == GateDecision.WAIT and result.reason in {"settling", "trailing_incomplete"}:
        deadline = time.monotonic() + max(gate.settle_seconds, 0.6)
        while time.monotonic() < deadline:
            time.sleep(0.1)
            result = gate.feed(text, speech_ended=True, is_interim=False)
            if result.decision != GateDecision.WAIT:
                break
        # After wait, if still trailing-incomplete, accept as finished anyway
        # so long pauses don't deadlock the loop.
        if result.decision == GateDecision.WAIT and result.reason == "trailing_incomplete":
            result = gate.force_evaluate(text, accept_incomplete=True)

    if result.decision == GateDecision.IGNORE:
        print(f"\r  (listening)          ", end="", flush=True)
        return

    if result.decision != GateDecision.READY:
        print(f"\r  … {result.text}          ", end="", flush=True)
        return

    final_text = result.text
    if final_text == _last_spoken_user:
        return

    _busy = True
    _last_spoken_user = final_text
    try:
        print(f"\r> {final_text}          ")

        new_mode = detect_mode(final_text, mode)
        if new_mode != mode:
            mode = new_mode
            print(f"  [switched to {mode} mode]")

        normalized = normalize(final_text)

        # Think quietly — do not speak until the full reply exists.
        print("  (thinking)", end="", flush=True)
        try:
            response_text, history = respond(normalized, history, mode=mode)
        except Exception as e:
            print(f"\r  [agent error: {e}]")
            return

        if not (response_text or "").strip():
            print("\r  [empty agent reply — staying quiet]")
            return

        speakable = style_speech(render_math(response_text)).strip()
        if not speakable:
            print("\r  [nothing to speak]")
            return

        print(f"\r< {speakable}          ")
        ding()
        speak(speakable)
    finally:
        _busy = False
        gate.reset()


# ------------------------------------------------------------------ #
#  Entry point
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    print("lilvro — voice STEM agent")
    print("Mode: walkthrough  |  Say 'quiz mode' / 'teach back' / 'help me' to switch")
    print("Pause: press p  or say 'pause lilvro' / 'resume'")
    print("I only answer after you finish speaking.")
    print("Press Ctrl+C to quit\n")

    threading.Thread(target=_keyboard_watcher, daemon=True).start()

    recorder = AudioToTextRecorder(
        model="tiny.en",
        language="en",
        compute_type="float32",
        silero_sensitivity=0.4,
        webrtc_sensitivity=NOISE_FILTER_LEVEL if NOISE_FILTER else 0,
        post_speech_silence_duration=POST_SPEECH_SILENCE,
        # Partials for the UI only — never trigger the agent.
        on_realtime_transcription_stabilized=on_partial,
    )

    try:
        while True:
            # recorder.text blocks until a silence-delimited utterance.
            recorder.text(on_transcript)
    except KeyboardInterrupt:
        print("\nGoodbye!")
        recorder.stop()
