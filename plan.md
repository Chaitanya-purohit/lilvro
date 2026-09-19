# lilvro — Plan

## Vision

An AI voice companion for STEM learning, designed to make mathematical and scientific knowledge **orally accessible**. Instead of copying LLM-generated answers, students are walked through problems via natural conversation with an agent that speaks math like a human does.

> `sqrt(x)` -> "square root of x" | `dy/dx` -> "the derivative of y with respect to x" | `H₂O` -> "H 2 O" | `A → B` -> "A yields B" (chemistry) or "A implies B" (logic)

---

## Target

- **Who**: Kids, primarily younger students (roughly 8-14)
- **Subject**: STEM — math, science, chemistry, engineering concepts
- **Niche**: Scientific communication via speech — the agent speaks and understands math and chemical notation naturally

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
- Agent interprets spoken math/chemistry and responds in natural spoken language
- Handles: arithmetic, algebra, calculus, matrices, scientific notation, chemical equations, units
- Built on **Whisper** (STT, open source) + **Claude** (reasoning + pedagogy) + **Deepgram Aura** (TTS only)

### 2. Teach-Back Mode (child teaches the AI)
Goal: the child becomes the explainer; the AI is the curious peer.

**Entry**
- Wake phrases: "let me teach you", "I'll explain", "teach-back", "can I explain"
- Or agent invites: "want to teach me that one?"

**Live loop (real-time)**
1. **Listen** — AI asks for the child's explanation; no lecture yet
2. **Probe** — if thin, ask for one concrete example / next step
3. **Intentional miss** — if vague or fuzzy, AI mildly misunderstands on purpose so the child must sharpen the idea
4. **Concept check** — if solid, ask one targeted check question and name what was strong
5. **Gap log** — weak spots stored in session (`teachback_gaps`) for later practice

**Exit**
- "stop teach-back", "normal mode", "back to studying"
- Or after a successful concept-check streak, AI offers to switch back

**Implementation**
- Local state machine in `modes.py` (`TeachbackState`) — no extra LLM hop
- Sticky mode in `tools.py` router so mid-explanation turns stay in teach-back instantly
- Prompt overlay injected each turn by `agent.py`

### 3. Mistake Mode (AI plants an error; child corrects it)
Also called Quiz Mode in product language. Goal: critical listening.

**Entry**
- Wake phrases: "mistake mode", "quiz me", "catch the mistake", "spot the error"

**Live loop (real-time)**
1. **Plant** — AI states one small, age-safe incorrect STEM claim + asks the child to check it
2. **Nudge** — if unclear, ask them to point at the suspicious bit
3. **Hint** — if they miss, one narrow hint (no full reveal)
4. **Reveal** — after two misses, kindly reveal + correct in one spoken sentence
5. **Caught** — if they fix it, celebrate, confirm why, offer another round or exit

**Exit**
- "stop mistake", "stop quiz", "normal mode"
- Or after a catch, child can decline another round

**Implementation**
- Local state machine in `modes.py` (`MistakeState`)
- Sticky until exit; hints/catches/misses tracked for mastery signals

### 4. Study / Problem Walkthrough Mode
- Student brings a problem; agent walks them through it step by step
- Never gives the final answer directly — guides via Socratic questioning
- Tracks which steps the student needed help on
- Default mode when no special wake phrase is active

---

## Tools (real-time recognition + soft adjust)

Tools are **not** separate apps. They are fast local intents the agent recognizes every turn, then overlays onto the reply. Routing is keyword/pattern based in `tools.py` — **zero extra model calls** so tool switches keep pace with live voice.

| Tool | When it fires | Behavior |
|---|---|---|
| **Mental Health** | Distress / high frustration / overwhelm language | Validate, slow down, offer break/easier step; never diagnose; serious distress → trusted adult |
| **Motivation** | Pep-talk asks, boredom, "why bother", light fatigue | Short specific encouragement + one tiny next win, then back to learning |
| **Teaching** | Default STEM help / explain / walkthrough | Socratic: one step, one question, spoken math |
| **Advising** | Study tips, "what next", how to approach a topic | Concrete micro-plan or practice advice |
| **Entertainment** | Disengagement / short-reply streaks / boredom | One vivid STEM analogy or wonder, then an easy re-entry question |

### Soft adjust (mid-turn, without fully leaving the lesson)
- Light frustration → keep **Teaching**, add **Motivation** support overlay
- Frustration streak ≥ 2 → keep task if possible, add **Mental Health** support overlay
- Distress keywords → **Mental Health** becomes primary immediately
- Special modes (teach-back / mistake) stay sticky; support tools can still ride along

### Latency path (must stay real-time)
```
normalized text
  -> collect_signals()     # precompiled regex, <1ms
  -> route_turn()          # sticky session + priority rules, <1ms
  -> mode engine           # teachback/mistake phase hint, <1ms
  -> build_instructions()  # short overlays only
  -> Codex Responses API   # max_output_tokens capped for short speech
  -> spoken reply
```
No second LLM for classification. Session state (`AgentRuntime`) carries tool/mode/streaks across turns.

---

## Emotional & Motivational Layer

### Mental Health — What it means in a voice agent
No screen means the only signal is **voice and words**. Emotional state is detected from:
- What they say: "I don't get it", "this is stupid", "I give up"
- Patterns: repeated wrong answers, very short responses, long pauses

The agent never diagnoses — it adjusts tone and difficulty, and redirects serious concerns to a trusted adult.

### Mood States
| Mood | Agent Response |
|---|---|
| `frustrated` | Slows down, offers encouragement, simplifies |
| `disengaged` | Switches to Entertainment tool — reframes topic interestingly |
| `confused` | Backtracks, re-explains from a different direction |
| `confident` | Pushes slightly harder, introduces next concept |

---

## Dashboard

| Component | Description |
|---|---|
| **Motivation** | Streaks, session goals, verbal encouragement moments logged |
| **Progression** | Topics covered, concepts unlocked, sessions completed |
| **Mastery / Understanding** | Per-topic confidence scores from Teach-Back and walkthroughs |
| **Activity** | Time spent, attention patterns, session history |

All feedback is spoken, never shown (no screen during session).

---

## Kid Safety Features

- **Content filtering**: Agent refuses to engage with off-topic content (social media, gaming, relationships)
- **Age-appropriate language**: Responses tuned for 8-14 year olds — no jargon, no adult themes
- **No personal data**: Agent never asks for name, location, school, or any identifying information
- **Safe messaging on mental health**: Follows safe messaging guidelines — never dismisses distress, always redirects to a trusted adult for serious concerns
- **Topic boundaries**: Strictly STEM — agent gracefully redirects non-STEM questions back to study
- **No internet access**: Agent cannot browse the web or reference external content
- **Distraction-free hardware**: Dedicated ESP32 device prevents access to games, social media, messaging

---

## Peer Persona

The agent talks like a slightly older student, not a teacher:
- Casual language: "okay so here's the thing about integrals..."
- Gets "excited" about topics
- Can be wrong sometimes (Quiz Mode)
- Name and personality TBD — critical for engagement with kids

---

## Voice Pipeline

### Architecture
```
Mic input
  -> Whisper STT (open source, local)
    -> speech_normalizer.py      (spoken text -> Unicode math/chemistry)
      -> mood_tracker.py         (classify student mood)
        -> tools.py / modes.py   (local tool+mode route, <1ms)
          -> agent.py              (Codex — tool overlays + Teach-Back / Mistake)
            -> motivation_engine.py  (streaks, encouragement)
            -> math_renderer.py    (Unicode math/chemistry -> speakable English)
              -> Deepgram Aura TTS  (natural voice output)
                -> Speaker
```

### One-line pipeline with Pipecat (open source)
Rather than manually chaining modules, use **Pipecat** (open source by Daily.co) which handles async audio streaming, interruptions, and turn-taking:

```python
pipeline = Pipeline([
    WhisperSTTService(),         # open source STT — local, free, no data sent out
    SpeechNormalizerService(),   # Chai's module
    MoodTrackerService(),        # Sam's module
    ToolRouterService(),         # Andy — local mental_health/motivation/teaching/advising
    ModeEngineService(),         # Andy — teachback + mistake state machines
    CodexAgentService(),         # Andy's module
    MathRendererService(),       # Kyle's module
    DeepgramAuraTTSService(),    # TTS — Deepgram used only for voice output
])
```

Routing and mode phase selection happen **before** the LLM so the spoken reply can adapt every turn without waiting on a classifier model.


### Why Whisper for STT
- Fully open source (MIT license), runs locally
- No per-minute cost, no student audio sent to third party
- Handles accented speech and kid voices well
- `faster-whisper` (CTranslate2) runs near-realtime on CPU

### Why Deepgram Aura for TTS only
- Natural, child-friendly voice
- Low latency REST call
- Already integrated — one key

---

## Tech Stack

| Layer | Tool | Notes |
|---|---|---|
| Speech-to-Text | Whisper / faster-whisper | Open source, local |
| LLM / Reasoning | Claude API (claude-sonnet-4-6) | Pedagogy + persona |
| Text-to-Speech | Deepgram Aura | Natural voice, REST, TTS only |
| Math parsing | `speech_normalizer.py` + `math_renderer.py` | Custom, bidirectional |
| Chemistry parsing | `chem_normalizer.py` (planned) | See below |
| Pipeline framework | Pipecat (open source) | Replaces manual chaining |
| Phone app (v1) | React Native or Flutter | Mic + speaker only |
| Hardware target (v2) | ESP32 | Same Deepgram REST in C++ |

---

## Math-to-Speech Layer

### Arrow `→` — Context-Aware Pronunciation

| Context | Expression | Spoken |
|---|---|---|
| Chemistry | `H₂ + O₂ → H₂O` | "H 2 plus O 2 yields H 2 O" |
| Equilibrium | `CaCO₃ ⇌ CaO + CO₂` | "calcium carbonate is in equilibrium with calcium oxide plus C O 2" |
| Logic | `A → B` | "A implies B" |
| Limits | `x → 0` | "x approaches 0" |
| Functions | `f: x → x²` | "f maps x to x squared" |

Domain is detected from context (surrounding symbols, keywords) before the rule is applied.

### Chemical Equations Support (`chem_normalizer.py`)

| Expression | Spoken |
|---|---|
| `H₂O` | "H 2 O" |
| `CO₂` | "C O 2" |
| `H₂SO₄` | "H 2 S O 4" |
| `Ca²⁺` | "calcium 2 plus ion" |
| `2H₂ + O₂ → 2H₂O` | "2 H 2 plus O 2 yields 2 H 2 O" |
| Subscripts `₂ ₃ ₄` | spoken as digits after element symbol |
| Coefficients | spoken as numbers before compound |

### Math expression examples

| Expression | Spoken form |
|---|---|
| `x^2` | "x squared" |
| `sqrt(x)` | "square root of x" |
| `dy/dx` | "the derivative of y with respect to x" |
| `int_a^b f(x) dx` | "the integral from a to b of f of x" |
| `lim_{x->0}` | "the limit as x approaches 0" |
| `[[1,2],[3,4]]` | "a 2 by 2 matrix, top row 1 and 2, bottom row 3 and 4" |
| `6.02e23` | "6 point 0 2 times 10 to the 23" |

---

## Andy-agent cohesion

Shared contracts live in `contracts.py` (`Tool`, `Mode`, `Phase`, signals, decisions, session, guidance).
Every andy-agent module consumes those types:

```
contracts.py  -> tools.py (route) -> modes.py (phase engines)
              -> persona.py (voice + local fallbacks)
              -> mastery.py (score from Phase)
              -> agent.py (AgentRuntime.turn orchestrator + math_renderer polish)
```

Pipeline callers should prefer one entrypoint:

```python
from agent import AgentRuntime
runtime = AgentRuntime.fresh()
reply = runtime.turn(normalized_text)          # full reply
planned = runtime.turn(normalized_text, plan_only=True)  # local routing only
```


```
transcribe.py          # mic -> Whisper STT -> transcript (Sam)
speech_normalizer.py   # spoken text -> Unicode math/chemistry (Chai)
symbols.json           # bidirectional symbol lexicon, 99 entries
math_renderer.py       # Unicode math -> speakable English (Kyle)
chem_normalizer.py     # chemical formula/equation -> speakable (Chai, planned)
contracts.py           # Shared Tool/Mode/Phase + turn contracts (Andy)
tools.py               # Fast local tool router + overlays (Andy)
modes.py               # Teach-back + mistake + walkthrough engines (Andy)
persona.py             # Peer personality + local fallbacks (Andy)
mastery.py             # Per-topic mastery scores (Andy)
voice_ux.py            # Barge-in, repeat, bookmarks, STT profiles, hardware cues (Andy)
agent.py               # AgentRuntime.turn orchestrator (Andy)
test_tools_modes.py    # Cohesion + router/mode unit tests (Andy)
test_voice_ux.py       # Voice conversation UX tests (Andy)
mood_tracker.py        # mood classification from transcript (Sam)
motivation_engine.py   # streaks, session goals, encouragement (Sam)
main.py                # Pipecat pipeline — chains all modules
```


---

## Team Branches

| Branch | Person | Owns |
|---|---|---|
| `chai-normalizer` | Chai | `speech_normalizer.py`, `chem_normalizer.py` |
| `kyle-renderer` | Kyle | `math_renderer.py`, `test_math_renderer.py` |
| `andy-agent` | Andy | `contracts.py`, `agent.py`, `tools.py`, `modes.py`, `persona.py`, `mastery.py`, `voice_ux.py` |
| `sam-voice` | Sam | `transcribe.py`, `mood_tracker.py`, `motivation_engine.py` |

---

## Build Phases

### Phase 1 — MVP (Hackathon)
- [x] Deepgram API test
- [x] `speech_normalizer.py` — spoken math -> Unicode (21 tests passing)
- [x] `symbols.json` — 99-entry bidirectional lexicon
- [x] `math_renderer.py` — Unicode -> speakable English (8 tests passing)
- [x] `transcribe.py` — live mic -> STT -> transcript (one-line display)
- [x] `voice_ux.py` — barge-in, repeat/rephrase, pause, bookmarks, STT profiles, personas, fillers, hardware cues
- [x] `contracts.py` — shared Tool/Mode/Phase turn contracts
- [x] `tools.py` — mental_health / motivation / teaching / advising / entertainment + soft adjust
- [x] `modes.py` — Teach-Back + Mistake + walkthrough phase engines
- [x] `persona.py` — peer personality + local safety/off-topic fallbacks
- [x] `mastery.py` — per-topic mastery scoring from Phase
- [x] `agent.py` — `AgentRuntime.turn` orchestrator + history + math_renderer polish + retries
- [x] `test_tools_modes.py` — cohesion + router/mode coverage
- [ ] TTS — Deepgram Aura REST call, play audio through speaker
- [ ] `main.py` — Pipecat pipeline connecting everything

### Phase 2 — Emotional Layer + Mode Depth
- [ ] `mood_tracker.py` — classify mood from transcript (feeds soft adjust)
- [ ] `motivation_engine.py` — streaks, encouragement, session goals
- [x] `persona.py` — peer personality wrapper
- [ ] Teach-Back: multi-topic gap review spoken at end of session
- [ ] Mistake Mode: difficulty ramp + topic packs (fractions, derivatives, chem)
- [x] Entertainment soft-tool for disengagement

### Phase 3 — Chemistry + Safety
- [ ] `chem_normalizer.py` — chemical formulas and equations
- [ ] Arrow `→` context detection (chemistry / logic / limits / functions)
- [ ] Kid safety content filter
- [ ] Safe messaging on mental health responses (expand beyond keyword gate)

### Phase 4 — Hardware
- [ ] Port voice loop to ESP32 (C++ HTTP client to Deepgram REST)
- [ ] Whisper offline fallback on device
- [ ] Keep tool/mode router on-device (already local, no cloud needed)

---

## Open Questions
- Do we need user accounts / persistence for the hackathon, or is session-only fine?
- What is the peer persona's name and character?
- Mode switching: wake phrases are implemented; should the agent also auto-invite teach-back after a successful walkthrough?
- How aggressive should intentional misunderstanding be for younger (8–10) vs older (11–14) kids?
