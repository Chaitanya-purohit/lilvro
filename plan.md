# lilvro — Plan

## Vision

An AI voice companion for STEM learning, designed to make mathematical and scientific knowledge **orally accessible**. Instead of copying LLM-generated answers, students are walked through problems via natural conversation with an agent that speaks math like a human does.

> `sqrt(x)` -> "square root of x" | `dy/dx` -> "the derivative of y with respect to x" | `[[1,2],[3,4]]` -> "a 2 by 2 matrix with top row 1 and 2, bottom row 3 and 4"

---

## Target

- **Who**: Kids, primarily younger students (roughly 8-14)
- **Subject**: STEM — math, science, engineering concepts
- **Niche**: Scientific communication via speech — the agent speaks and understands math notation naturally

---

## Core Philosophy

- Kids should **study with the agent**, not copy from it
- The agent acts as a **peer**, not a tutor — less intimidating, more conversational
- **No screen. No UI.** Purely voice in, voice out — the interface is the conversation itself
- No distraction: designed eventually for a dedicated ESP32 device; for now runs on a phone (mic + speaker only)

---

## Key Modes

### 1. Voice STEM Agent (Core)
- Fully voice-driven: student speaks, agent speaks back — no screen, no typing
- Student can state a problem verbally: "what is the integral of x squared from 0 to 1?"
- Agent interprets spoken math and responds in natural spoken math
- Handles: arithmetic, algebra, square roots, exponents, calculus (derivatives, integrals, limits), matrices, scientific notation, units
- Built on **Deepgram** (STT) + **Claude** (reasoning + pedagogy) + TTS

### 2. Teach-Back Mode
- Student explains a concept to the agent
- Agent listens, then asks concept-check questions
- Agent can intentionally misunderstand a poorly explained concept to push the student to be more precise
- Flags and stores weak areas per topic

### 3. Mistake Mode
- Agent deliberately explains something incorrectly
- Student must identify and correct the error
- If student misses it, agent gives a hint
- If student catches it, agent confirms and explains why
- Builds critical thinking and deeper understanding

### 4. Study / Problem Walkthrough Mode
- Student brings a problem; agent walks them through it step by step
- Never gives the final answer directly — guides via Socratic questioning
- Tracks which steps the student needed help on

---

## Emotional & Motivational Layer

### Mental Health — What it means in a voice agent
No screen means the only signal is **voice and words**. Emotional state is detected from:
- What they say: "I don't get it", "this is stupid", "I give up"
- Patterns: repeated wrong answers, very short responses, long pauses

The agent never diagnoses — it adjusts tone and difficulty in response.

### Mood States
| Mood | Agent Response |
|---|---|
| `frustrated` | Slows down, offers encouragement, simplifies |
| `disengaged` | Switches tone, reframes the topic more interestingly |
| `confused` | Backtracks, re-explains from a different direction |
| `confident` | Pushes slightly harder, introduces next concept |

### Motivation
- Streak of correct answers -> agent celebrates verbally
- First time mastering a topic -> special acknowledgement
- Struggling too long -> agent offers a hint or suggests a break
- Session goals: agent sets a small goal at the start ("let's get through derivatives today")

All feedback is spoken, never shown.

---

## Peer Persona

The agent talks like a slightly older student, not a teacher:
- Casual language: "okay so here's the thing about integrals..."
- Gets "excited" about topics
- Can be wrong sometimes (Mistake Mode)
- Name and personality TBD — critical for engagement with kids

---

## Tech Stack

| Layer | Tool |
|---|---|
| Speech-to-Text | Deepgram |
| LLM / Reasoning | Claude API (claude-sonnet-4-6) |
| Text-to-Speech | Deepgram Aura or ElevenLabs |
| Math parsing | Custom notation-to-speech layer |
| Phone app (v1) | React Native or Flutter |
| Hardware target (v2) | ESP32 (same Deepgram REST call in C++) |

---

## Math-to-Speech Layer (Key Differentiator)

Since there is no screen, all math must flow through speech in both directions:

- **STT -> structured math**: Deepgram transcribes student speech; a normalizer maps spoken phrases into structured math for Claude to reason over
- **Structured math -> TTS**: Claude's response is passed through a math-to-speech renderer before TTS, so the agent never says "sqrt x" or "x caret 2" aloud

| Expression | Spoken form |
|---|---|
| `x^2` | "x squared" |
| `x^n` | "x to the power of n" |
| `sqrt(x)` | "square root of x" |
| `cbrt(x)` | "cube root of x" |
| `dy/dx` | "the derivative of y with respect to x" |
| `d^2y/dx^2` | "the second derivative of y with respect to x" |
| `int_a^b f(x) dx` | "the integral from a to b of f of x" |
| `lim_{x->0}` | "the limit as x approaches 0" |
| `[[1,2],[3,4]]` | "a 2 by 2 matrix, top row 1 and 2, bottom row 3 and 4" |
| `6.02e23` | "6 point 0 2 times 10 to the 23" |

---

## Codebase Structure

```
voice_loop.py          # mic input, Deepgram STT, TTS playback
speech_normalizer.py   # spoken text -> math-normalized text
math_renderer.py       # math expressions -> speakable English
agent.py               # Claude calls, Socratic mode, Teach-Back, Mistake Mode
mood_tracker.py        # classifies student mood from transcript
motivation_engine.py   # streaks, encouragement, session goals
persona.py             # wraps Claude responses in peer personality
main.py                # integration: chains all modules together
```

### Full pipeline

```
voice_loop.listen()
  -> speech_normalizer.normalize()
    -> mood_tracker.classify()
      -> agent.ask()  [with mood context + persona]
        -> motivation_engine.check()
          -> math_renderer.render()
            -> voice_loop.speak()
```

---

## Team Split

| Branch | Person | Owns | Can test without audio |
|---|---|---|---|
| `Chai` | Chai | `voice_loop.py` | No — this is the audio layer |
| `Kyle` | Kyle | `math_renderer.py`, `speech_normalizer.py` | Yes — pure string in, string out |
| `Sam` | Sam | `mood_tracker.py`, `motivation_engine.py` | Yes — feed transcripts, assert mood + response |
| `Andy` | Andy | `agent.py`, `persona.py` | Yes — type input, print Claude response |

Integration: one `main.py` PR to main once all modules work independently.

---

## Build Phases

### Phase 1 — MVP (Hackathon)
- [x] Deepgram API test
- [ ] `voice_loop.py` — mic -> STT -> TTS
- [ ] `speech_normalizer.py` — spoken math -> structured math
- [ ] `math_renderer.py` — structured math -> speakable English
- [ ] `agent.py` — Socratic walkthrough via Claude
- [ ] `main.py` — integrate full pipeline

### Phase 2 — Emotional Layer
- [ ] `mood_tracker.py` — classify mood from transcript
- [ ] `motivation_engine.py` — streaks, encouragement, session goals
- [ ] `persona.py` — peer personality wrapper

### Phase 3 — Agent Modes
- [ ] Teach-Back mode
- [ ] Mistake Mode
- [ ] Topic/mastery tracking per session

### Phase 4 — Hardware
- [ ] Port voice loop to ESP32 (C++ HTTP client to Deepgram REST)
- [ ] Offline fallback for basic interactions

---

## Open Questions
- Do we need user accounts / persistence for the hackathon, or is session-only fine?
- What is the peer persona's name and character?
- How does the student switch modes — wake phrase ("let's do teach-back") or agent infers from context?
