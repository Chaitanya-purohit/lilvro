# Lil-Vro

**A voice-only STEM study buddy for kids aged 8–14.** No screen. No typing. Just talking through problems with a peer who guides instead of giving answers.

```
You speak  →  Lil-Vro listens  →  Lil-Vro guides (never just hands over the answer)  →  you hear it
```

Built at **HackMIT**. <!-- TODO: add Devpost link + demo video link -->

---

## Why we built it

Kids with a chatbot tend to copy answers. Kids who talk a problem through actually learn it. Lil-Vro is designed around that: it acts like a slightly older classmate, asks one leading question at a time, and makes the child do the thinking.

It also solves a problem most voice assistants ignore: **speaking math out loud**. Saying "x squared plus 2x equals 0" should be understood as an equation, and the answer should come back as natural speech, not garbled symbols.

---

## What it does

- **Spoken math and chemistry.** Understands things like "square root of x", "the derivative of y with respect to x", and "H 2 O", and speaks equations back the way a person would.
- **Socratic tutoring.** Asks leading questions and works step by step. It never simply gives the final answer.
- **Three learning modes.**
  - **Walkthrough** (default): the student brings a problem and gets guided through it.
  - **Teach-back:** the child explains a concept and Lil-Vro plays the curious peer, probing and asking check questions.
  - **Mistake mode / quiz:** Lil-Vro plants a small deliberate error and the child has to catch it.
- **Mood-aware.** Notices frustration, confusion, confidence, or disengagement from what the student says and adjusts its tone and difficulty.
- **Answer verification.** Built to never confirm a wrong answer as correct, and to admit uncertainty instead of making things up.
- **Kid-safety layer.** Age-appropriate content filtering on every reply, and off-topic questions get steered back to STEM.
- **Real hardware.** A prototype on an **ESP32-S3-BOX-3** streams the child's voice to Lil-Vro and plays the reply back, so it works as a standalone talking device.
- **Parent dashboard.** A Next.js + Supabase web app showing streaks, topics covered, per-topic mastery, and session history.

---

## How it works

```
Mic (laptop)                              ESP32-S3-BOX-3 (Wi-Fi)
 └─ RealtimeSTT (faster-whisper, local)    └─ 16 kHz PCM → box3_audio_server → Deepgram STT
     └─────────────────┬─────────────────────────────┘
                       ▼
        Utterance gate (wait until the student is done talking)
         └─ speech_normalizer / chem_normalizer   (spoken words → math & chemistry notation)
             └─ agent.py + tools + modes + mood   (OpenAI LLM, Socratic prompts, local routing)
                 └─ content_filter                (age-appropriate check on the reply)
                     └─ math_renderer / chem_render   (notation → speakable English)
                         └─ speech_styler             (more natural phrasing)
                             └─ Text-to-speech → Speaker (laptop or BOX-3)
                                 └─ session_store → Supabase → parent dashboard
```

Tool and mode routing (motivation, mental-health support, advising, entertainment, teach-back, mistake mode) uses fast local rules, so switching feels instant and needs no extra model call.

| Layer | Tech |
|---|---|
| Speech-to-text | RealtimeSTT with faster-whisper (`tiny.en`) locally; Deepgram streaming for the BOX-3 |
| LLM | OpenAI chat completions (default `gpt-4o`, override with `CODEX_MODEL`) |
| Text-to-speech | Deepgram Aura (laptop); OpenAI TTS (BOX-3) |
| Hardware | ESP32-S3-BOX-3 |
| Database | Supabase (Postgres, Auth, migrations) |
| Parent dashboard | Next.js (Vercel-ready) |

---

## Quick start

**You'll need:** Python 3.10+, a microphone and speakers, and API keys for [Deepgram](https://console.deepgram.com) and [OpenAI](https://platform.openai.com).

```bash
# 1. Clone
git clone https://github.com/Chaitanya-purohit/lilvro.git
cd lilvro

# 2. System audio library (needed by the mic input)
#    macOS:  brew install portaudio
#    Linux:  sudo apt install portaudio19-dev
#    Windows: nothing extra

# 3. Python dependencies
pip install -r requirements.txt

# 4. Add your keys
cp .env.example .env      # then open .env and fill in the values

# 5. Run
python main.py
```

Audio playback works on macOS (`afplay`), Windows (`winsound`), and Linux (`aplay`).

### Environment variables

Set these in `.env`. **Never commit this file** (it's gitignored).

```
DEEPGRAM_API_KEY=...            # text-to-speech (and BOX-3 speech-to-text)
DEEPGRAM_VOICE=aura-2-thalia-en
OPENAI_API_KEY=...              # LLM (and BOX-3 text-to-speech)
CODEX_MODEL=gpt-4o              # any OpenAI chat model ID

# Optional: parent dashboard persistence
# SUPABASE_URL=http://127.0.0.1:54321
# SUPABASE_SERVICE_ROLE_KEY=...
# CHILD_ID=bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb
```

---

## Using it

**Keyboard:** `p` pauses or resumes the mic. `Ctrl+C` quits.

**Voice commands:**

| Say | What happens |
|---|---|
| "pause lilvro" / "stop listening" / "go to sleep" | Pause |
| "resume" / "wake up" / "start listening" | Resume |
| "quiz mode" / "quiz me" / "find the mistake" | Mistake mode |
| "teach back" / "let me explain" / "I'll explain" | Teach-back mode |
| "help me" / "walk me through" | Walkthrough mode |

**Things to try in a demo:**
- "Help me solve 3x plus 2 equals 17"
- "Quiz me on fractions"
- "Let me explain how square roots work"
- Sound frustrated ("I give up, this is stupid") and listen to the tone change

**Audio tuning:** `main.py` has toggles at the top for `NOISE_FILTER` (levels 1–3) and `ECHO_CANCEL`, which ignores the mic briefly after Lil-Vro speaks so it doesn't hear itself.

---

## Hardware: ESP32-S3-BOX-3

Lil-Vro is meant to live on a dedicated, distraction-free device. The prototype uses an **ESP32-S3-BOX-3**: the device captures 16 kHz mono audio and streams it over Wi-Fi to a server on the same network. That server (`box3_audio_server.py`) transcribes it with Deepgram, runs it through the same normalizer and agent as the laptop version, generates the spoken reply, and sends the audio back to the device to play.

```bash
# on the laptop, connected to the same Wi-Fi as the BOX-3
python box3_audio_server.py          # listens on port 8787 by default
```

> The BOX-3 transport currently lives on the `socrates-bot` branch and has not been merged into `main` yet.

---

## Parent dashboard and database

Parents see their child's progress in a Next.js dashboard backed by **Supabase**. The database (schema migrations, seed data, and auth) runs on local Supabase now and hosted Supabase + Vercel later, with the same schema, so going live only means swapping the URL and keys.

```bash
# 1. Start local Supabase (needs Docker)
npx supabase start
npx supabase db reset          # migrations + seed data
npx supabase status            # copy the API URL and keys

# 2. Start the dashboard
cp dashboard/.env.local.example dashboard/.env.local
# fill in NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
cd dashboard && npm install && npm run dev
```

Open http://127.0.0.1:3000 and sign in with the demo account `parent@lilvro.local` / `password123`.

To save real voice sessions to the dashboard, set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `CHILD_ID` in the root `.env`, then run `python main.py`. Turns are written as you talk, and `Ctrl+C` ends the session and updates streaks. If those variables are unset, Lil-Vro works normally and nothing is stored.

Deploying to Vercel: see [`dashboard/README.md`](dashboard/README.md).

---

## Tests

```bash
python -m pytest test_math_renderer.py test_tools_modes.py test_utterance_gate.py test_voice_ux.py -v
```

`test_deepgram.py` needs a real `DEEPGRAM_API_KEY` and makes a live API call.

---

## Project structure

```
main.py               Entry point: the full voice loop
agent.py              LLM brain: history, modes, mood, guardrails, orchestration
contracts.py          Shared Tool / Mode / Phase types
tools.py              Fast local tool router (motivation, support, advising, ...)
modes.py              Teach-back, mistake, and walkthrough state machines
persona.py            Peer personality and local fallbacks
mastery.py            Per-topic mastery scoring
mood_tracker.py       Mood classification and session stats
content_filter.py     Age-appropriate filtering of replies
voice_ux.py           Barge-in, repeat/rephrase, bookmarks, STT profiles
utterance_gate.py     Only respond once the student has finished speaking
speech_normalizer.py  Spoken math → notation
chem_normalizer.py    Spoken/written chemistry ↔ notation
math_renderer.py      Notation → speakable English
speech_styler.py      Natural-sounding phrasing for TTS
transcribe.py         Standalone mic transcription test
session_store.py      Supabase persistence for voice sessions
symbols.json          Math symbol lexicon
chem_symbols.json     Chemistry symbol lexicon
dashboard/            Next.js parent dashboard
supabase/             Migrations, seed data, local config
sounds/               Audio cues
```

On the `socrates-bot` branch: `box3_audio_server.py` (BOX-3 audio transport) and `teachback.py` (teach-back prompt).

---

## Privacy and safety notes

- On the laptop, speech recognition runs **locally**; raw audio isn't sent to a third party.
- On the **BOX-3** path, the child's audio is streamed to **Deepgram** for transcription.
- Transcribed text is sent to **OpenAI** for replies, and reply text goes to a text-to-speech service (Deepgram or OpenAI) for voice.
- Lil-Vro is designed not to ask for names, locations, schools, or other identifying information.
- Draft [Terms & Conditions](terms_and_conditions.md) and [Privacy Policy](privacy_policy.md) are included.
- This is a hackathon prototype with no parental-consent flow yet, so it isn't ready for unsupervised use with children at scale.

---

## Known limitations

- English only (`tiny.en` speech model on the laptop path).
- Conversation history is in memory unless Supabase is configured.
- The LLM defaults to `gpt-4o`, which costs money per request. Set `CODEX_MODEL` to a cheaper model if needed.
- The BOX-3 prototype needs a laptop on the same Wi-Fi to do the processing; it doesn't run standalone yet.

---

## Roadmap

- Make the BOX-3 fully standalone, with on-device wake word and fewer laptop dependencies.
- More Mistake Mode topic packs (fractions, derivatives, chemistry) and a difficulty ramp.
- End-of-session spoken review of the concepts a child struggled with in teach-back.
- Broader safe-messaging responses beyond the current keyword checks.
- A parental-consent flow.

---

## Team

| Who | What they built | Languages & skills | Key features |
|---|---|---|---|
| **Chai** | The core voice pipeline and agent, the spoken-math and chemistry normalizers, local speech-to-text, and the project's legal docs. | Python, JSON lexicons, regular expressions, prompt engineering, audio processing, technical writing. | Spoken math and chemistry, noise filtering, echo cancellation, natural-sounding speech, mood tracker, content filter, answer-verification guardrails. |
| **Kyle** | The math-to-speech renderer, kid-safety guardrails, mood detection, and an OpenAI adapter for classifying messages. | Python, OpenAI API, Deepgram text-to-speech, text parsing, unit testing, cross-platform audio. | Equations spoken as natural English, safe age-appropriate replies, mood-based tone, Deepgram voice, Windows playback. |
| **Andy** | The Supabase database, session storage, the Next.js parent dashboard, the utterance gate, and the agent's shared structure. | TypeScript, SQL, Python, React and Next.js, Tailwind CSS, Supabase (Postgres, Auth, row-level security), database design. | Saved sessions and streaks, mastery and activity views, parent login, turn-taking that waits for the child to finish, barge-in and bookmarks. |
| **Sam** | The ESP32-S3-BOX-3 hardware voice transport, the teach-back prompt, and the first live microphone transcription. | Python (asyncio), WebSockets and TCP sockets, raw PCM audio, Deepgram and OpenAI APIs, embedded hardware. | Live voice streaming from the device over Wi-Fi, speech-to-text, spoken replies played on the device, teach-back mode. |
