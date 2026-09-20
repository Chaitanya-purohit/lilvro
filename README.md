# lilvro

A voice-only STEM learning companion for students aged 8–14. No screen. No typing. Just talking through problems. Optional **parent dashboard** (Next.js + Supabase) for session history.

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
#   OPENAI_API_KEY     — from platform.openai.com
```

---

## Environment variables

```
DEEPGRAM_API_KEY=...         # Text-to-speech (Deepgram Aura)
DEEPGRAM_VOICE=aura-2-thalia-en
OPENAI_API_KEY=...           # LLM inference (OpenAI)
CODEX_MODEL=gpt-4o           # Override with any OpenAI model ID

# Optional — parent dashboard persistence
# SUPABASE_URL=http://127.0.0.1:54321
# SUPABASE_SERVICE_ROLE_KEY=...
# CHILD_ID=bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb
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

## Parent dashboard (local)

Uses the same schema for local Docker Supabase and hosted Supabase later (swap URL/keys only).

### 1. Start local Supabase

Requires [Docker](https://docs.docker.com/get-docker/) and the Supabase CLI:

```bash
npx supabase start
npx supabase db reset   # migrations + seed.sql
npx supabase status     # copy API URL, anon key, service_role key
```

### 2. Dashboard env

```bash
cp dashboard/.env.local.example dashboard/.env.local
# fill NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
cd dashboard && npm install && npm run dev
```

Open http://127.0.0.1:3000

Demo login (from `supabase/seed.sql`): `parent@lilvro.local` / `password123`
Seeded child id: `bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb`

### 3. Persist voice sessions into the DB

Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `CHILD_ID` in root `.env`, then run `python main.py`. Turns are written as you talk; Ctrl+C ends the session and updates streaks. If those vars are unset, the voice loop still runs (store is a no-op).

### Hosted later (Vercel)

1. Hosted Supabase project + `npx supabase db push`
2. Vercel project with **Root Directory** = `dashboard`
3. Set `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (and optional service role)
4. Allow your Vercel URL in Supabase Auth redirect URLs

See [`dashboard/README.md`](dashboard/README.md) for the full checklist.

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
session_store.py      # Agent → Supabase writes (optional)
speech_normalizer.py  # Spoken text → math notation (for LLM)
math_renderer.py      # Math notation → speakable text (for TTS)
utterance_gate.py     # Only respond when student has finished speaking
symbols.json          # 99-entry bidirectional math symbol lexicon
transcribe.py         # Standalone mic transcription test
supabase/             # Migrations, seed, local config
dashboard/            # Next.js parent UI
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
- **LLM costs** — defaults to `gpt-4o`; change `CODEX_MODEL` if you need a cheaper model.
- **English only** — STT uses `tiny.en`.
- **Optional persistence** — without Supabase env vars, conversation history is in-memory and clears on exit.

---

## Team branches

| Branch | Owner | Module |
|---|---|---|
| `chai-normalizer` | Chai | `speech_normalizer.py`, `transcribe.py` |
| `kyle-renderer` | Kyle | `math_renderer.py` |
| `andy-agent` | Andy | `agent.py`, `main.py` |
| `sam-voice` | Sam | `transcribe.py` (mic input) |
