# lilvro

A voice-only STEM learning companion for students aged 8–14. No screen. No typing. Just talking through problems.

```
You speak → lilvro listens → lilvro guides (never just gives the answer) → you hear the response
```

---

## What it does

- **Spoken math** — say "x squared plus 2x equals 0" and lilvro understands it as math, not text
- **Socratic tutoring** — asks leading questions instead of handing over answers
- **Three modes** — walkthrough, teach-back, quiz (with a deliberate mistake to find)
- **Mood-aware** — adjusts tone when you sound frustrated or disengaged
- **Answer verification** — will never confirm a wrong answer as correct

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 or later |
| macOS | Required (uses `afplay` for audio playback) |
| Microphone | Built-in or external |

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/Chaitanya-purohit/lilvro.git
cd lilvro

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install system audio (macOS)
brew install portaudio

# 4. Copy and fill in your API keys
cp .env.example .env
# Edit .env and add:
#   DEEPGRAM_API_KEY   — from console.deepgram.com
#   OPENROUTER_API_KEY — from openrouter.ai
```

---

## Environment variables

```
DEEPGRAM_API_KEY=...         # Text-to-speech (Deepgram Aura)
OPENROUTER_API_KEY=...       # LLM inference (OpenRouter free tier)
CODEX_MODEL=openrouter/free  # Override with any OpenRouter model ID
```

---

## Running

```bash
python main.py
```

**Keyboard controls:**
- `p` — pause / resume the microphone
- `Ctrl+C` — quit

**Voice commands:**
- `"pause lilvro"` / `"stop listening"` — pause
- `"resume"` / `"wake up"` — resume
- `"quiz mode"` / `"quiz me"` — switch to quiz mode
- `"teach back"` / `"let me explain"` — switch to teach-back mode
- `"help me"` / `"walk me through"` — switch to walkthrough mode

---

## Running tests

```bash
python -m pytest test_speech_normalizer.py test_math_renderer.py -v
```

The speech normalizer has 21 tests and the math renderer has 8 tests, all passing.

---

## Project structure

```
main.py               # Full voice pipeline (entry point)
agent.py              # LLM brain — history, modes, mood, guardrails
speech_normalizer.py  # Spoken text → math notation (for LLM)
math_renderer.py      # Math notation → speakable text (for TTS)
utterance_gate.py     # Only respond when student has finished speaking
symbols.json          # 99-entry bidirectional math symbol lexicon
transcribe.py         # Standalone mic transcription test
.env.example          # API key template
requirements.txt      # Python dependencies
```

---

## Architecture

```
Mic
 └─ RealtimeSTT (faster-whisper, local)
     └─ UtteranceGate (wait for silence)
         └─ speech_normalizer (spoken → math)
             └─ agent.py → OpenRouter LLM
                 └─ math_renderer (math → spoken)
                     └─ Deepgram TTS
                         └─ afplay (speaker)
```

---

## Known limitations

- **macOS only** — audio playback uses `afplay`. Linux/Windows requires replacing this with `aplay` or `sounddevice`.
- **No parental consent flow** — not yet suitable for unsupervised child use at scale.
- **Free LLM tier** — `openrouter/free` routes to whichever free model is available. Pin a specific model for consistency.
- **English only** — STT uses `tiny.en`.
- **No persistent sessions** — conversation history is in-memory and clears on exit.

---

## Team branches

| Branch | Owner | Module |
|---|---|---|
| `chai-normalizer` | Chai | `speech_normalizer.py`, `transcribe.py` |
| `kyle-renderer` | Kyle | `math_renderer.py` |
| `andy-agent` | Andy | `agent.py`, `main.py` |
| `sam-voice` | Sam | `transcribe.py` (mic input) |
