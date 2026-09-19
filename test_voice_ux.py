"""Tests for voice / conversation UX controls."""

from agent import AgentRuntime
from voice_ux import (
    LanguageCode,
    PeerVoice,
    SpeakDistance,
    SttProfile,
    TranscriptEvent,
    VoiceIntent,
    VoiceUxState,
    confidence_should_reask,
    detect_voice_intent,
    handle_voice_ux,
    hardware_payload,
    listening_cues,
    say_another_way,
    speak_slower,
    thinking_filler,
)


def test_barge_in_and_pause_resume():
    state = VoiceUxState()
    barge = handle_voice_ux("wait hold on", state)
    assert barge.intent == VoiceIntent.BARGE_IN
    assert barge.stop_tts is True
    pause = handle_voice_ux("lilvro, pause", state)
    assert state.paused is True
    blocked = handle_voice_ux("help me with fractions", state)
    assert blocked.handled is True
    assert "pause" in (blocked.speak or "").lower()
    resume = handle_voice_ux("lilvro, continue", state)
    assert state.paused is False
    assert resume.intent == VoiceIntent.RESUME


def test_repeat_slower_and_another_way():
    state = VoiceUxState()
    state.remember_agent("Therefore we utilize the derivative to calculate slope.")
    slower = handle_voice_ux("say that slower", state)
    assert slower.intent == VoiceIntent.REPEAT_SLOWER
    assert "slower" in (slower.speak or "").lower()
    other = handle_voice_ux("say it another way", state)
    assert other.intent == VoiceIntent.SAY_ANOTHER_WAY
    assert "another way" in (other.speak or "").lower()
    assert "use" in (other.speak or "").lower() or "figure out" in (other.speak or "").lower()


def test_bookmarks_and_go_back():
    state = VoiceUxState()
    state.remember_agent("First we look at the integral from 0 to 1.")
    state.remember_agent("Next multiply both sides by x.")
    marked = handle_voice_ux("bookmark this", state)
    assert marked.intent == VoiceIntent.BOOKMARK
    back = handle_voice_ux("go back", state)
    assert back.intent == VoiceIntent.GO_BACK
    assert "integral" in (back.speak or "").lower() or "multiply" in (back.speak or "").lower()
    # Label the bookmark then recall
    state.bookmarks.add("integral", "First we look at the integral from 0 to 1.", topic="integral")
    recall = handle_voice_ux("go back to the integral part", state)
    assert recall.intent == VoiceIntent.RECALL_BOOKMARK
    assert "integral" in (recall.speak or "").lower()


def test_persona_language_distance():
    state = VoiceUxState()
    persona = handle_voice_ux("switch to calm", state)
    assert state.persona == PeerVoice.CALM
    assert persona.handled
    lang = handle_voice_ux("speak in spanish", state)
    assert state.stt.language == LanguageCode.ES
    dist = handle_voice_ux("whisper mode", state)
    assert state.stt.distance == SpeakDistance.WHISPER
    assert dist.updated.get("gain") == state.stt.input_gain()


def test_stt_profiles_and_confidence():
    profile = SttProfile(kid_speech=True, distance=SpeakDistance.WHISPER, noise_robust=True)
    whisper = profile.whisper_options()
    assert whisper["vad_filter"] is True
    assert "child" in whisper["initial_prompt"].lower() or "math" in whisper["initial_prompt"].lower()
    deepgram = profile.deepgram_options()
    assert deepgram["interim_results"] is True
    assert "fraction" in deepgram["keywords"]
    low = TranscriptEvent("um", confidence=0.2, is_final=True)
    assert confidence_should_reask(low, profile) is True
    high = TranscriptEvent("help with fractions", confidence=0.9, is_final=True)
    assert confidence_should_reask(high, profile) is False


def test_hardware_and_fillers():
    from voice_ux import HardwareCue

    data = hardware_payload(HardwareCue.LISTENING)
    assert "led_rgb" in data
    assert thinking_filler(LanguageCode.EN)
    cues = listening_cues(VoiceUxState())
    assert "stt" in cues and "whisper" in cues


def test_delivery_helpers():
    assert "slower" in speak_slower("This is a longer sentence that should pace out for kids.").lower()
    assert "another way" in say_another_way("Therefore we calculate the value.").lower()


def test_agent_runtime_voice_ux_integration():
    runtime = AgentRuntime.fresh()
    runtime.voice.remember_agent("The derivative of x squared is 2 x.")
    reply = runtime.turn("say that slower")
    assert reply.local_only is True
    assert reply.voice_intent == VoiceIntent.REPEAT_SLOWER.value
    assert reply.stop_tts is False
    pause = runtime.turn("lilvro, pause")
    assert pause.stop_tts is True
    uncertain = runtime.turn("mmm", confidence=0.1)
    assert uncertain.reason == "stt_uncertain"
    assert detect_voice_intent("wait").intent == VoiceIntent.BARGE_IN


if __name__ == "__main__":
    test_barge_in_and_pause_resume()
    test_repeat_slower_and_another_way()
    test_bookmarks_and_go_back()
    test_persona_language_distance()
    test_stt_profiles_and_confidence()
    test_hardware_and_fillers()
    test_delivery_helpers()
    test_agent_runtime_voice_ux_integration()
    print("all voice_ux tests passed")
