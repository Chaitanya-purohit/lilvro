"""Fast unit checks for local tool routing, modes, mastery, and agent planning."""

from agent import AgentRuntime, plan_turn, respond
from mastery import MasteryBook
from modes import MistakeState, TeachbackState, guide_mistake, guide_teachback, guide_walkthrough
from persona import persona_base_prompt
from tools import Mode, SessionState, Tool, collect_signals, extract_topic, route_turn


def test_mental_health_overrides():
    decision = route_turn("I'm overwhelmed and I can't breathe")
    assert decision.primary_tool == Tool.MENTAL_HEALTH
    assert decision.adjust is True


def test_distress_is_local_and_instant():
    runtime = AgentRuntime.fresh()
    reply = respond("I feel hopeless and want to disappear", runtime=runtime)
    assert reply.local_only is True
    assert "trusted adult" in reply.text.lower()
    assert reply.tool == Tool.MENTAL_HEALTH


def test_off_topic_is_local():
    reply = respond("can we talk about fortnite instead", runtime=AgentRuntime.fresh())
    assert reply.local_only is True
    assert "STEM" in reply.text or "stem" in reply.text.lower() or "fractions" in reply.text.lower()


def test_teachback_wake_topic_and_sticky():
    session = SessionState()
    first = route_turn("let me teach you about fractions", session)
    assert first.mode == Mode.TEACHBACK
    assert first.topic == "fractions"
    session.mode = Mode.TEACHBACK
    session.topic = "fractions"
    second = route_turn("so a fraction is like part of a whole", session)
    assert second.mode == Mode.TEACHBACK
    assert second.reason == "sticky_teachback"


def test_mistake_wake():
    decision = route_turn("quiz me and make me catch the mistake")
    assert decision.mode == Mode.MISTAKE


def test_advising_motivation_entertainment():
    assert route_turn("how should I study for algebra").primary_tool == Tool.ADVISING
    assert route_turn("I need a pep talk").primary_tool == Tool.MOTIVATION
    session = SessionState(short_reply_streak=3)
    assert route_turn("idk", session).primary_tool == Tool.ENTERTAINMENT


def test_frustration_soft_adjust():
    session = SessionState(tool=Tool.TEACHING, frustration_streak=2)
    decision = route_turn("this is too hard and I don't get it", session)
    assert decision.adjust is True
    assert decision.support_tool in {Tool.MENTAL_HEALTH, Tool.MOTIVATION}


def test_teachback_phases():
    state = TeachbackState()
    state.start("gravity")
    first = guide_teachback("let me teach you gravity", state)
    assert first.phase == "listen"
    second = guide_teachback("it's like stuff that pulls things", state)
    assert second.phase == "intentional_miss"
    assert state.gaps
    third = guide_teachback(
        "gravity is a force that pulls objects together because of mass, "
        "like earth pulling an apple down",
        state,
    )
    assert third.phase == "concept_check"


def test_mistake_catch_hint_and_ramp():
    state = MistakeState()
    plant = guide_mistake("quiz me about fractions", state)
    assert plant.phase == "plant_mistake"
    assert state.topic == "fractions"
    caught = guide_mistake("actually that's wrong, it should be squared", state)
    assert caught.phase == "caught"
    again = guide_mistake("another one", state)
    assert again.phase == "plant_mistake"


def test_walkthrough_phases():
    session = SessionState()
    orient = guide_walkthrough("help me with fractions", session)
    assert orient.phase == "orient"
    session.turns = 3
    session.topic = "fractions"
    step = guide_walkthrough("okay what next", session)
    assert step.phase in {"step", "check", "orient"}
    session.frustration_streak = 2
    stuck = guide_walkthrough("I don't get it", session)
    assert stuck.phase == "stuck"


def test_mastery_updates():
    book = MasteryBook()
    book.note_turn(topic="fractions", engagement=True)
    book.note_turn(topic="fractions", mistake_catch=True)
    assert book.get("fractions") > 0.35
    assert "fractions" in book.coaching_line("fractions")


def test_plan_turn_walkthrough_and_mastery_path():
    runtime = AgentRuntime.fresh()
    planned, runtime = plan_turn("walk me through the integral of x", runtime)
    assert planned.decision.primary_tool == Tool.TEACHING
    assert planned.guidance.phase in {"orient", "step", "check"}
    assert runtime.session.turns == 1
    assert persona_base_prompt().startswith("You are lilvro")


def test_extract_topic():
    assert extract_topic("let me teach you about derivatives") == "derivatives"
    assert extract_topic("quiz me about gravity") == "gravity"
    assert extract_topic("help me with photosynthesis") == "photosynthesis"


def test_signal_collection_is_cheap():
    signals = collect_signals("I give up, this is stupid")
    assert signals.frustration >= 1
    assert signals.word_count >= 4


if __name__ == "__main__":
    test_mental_health_overrides()
    test_distress_is_local_and_instant()
    test_off_topic_is_local()
    test_teachback_wake_topic_and_sticky()
    test_mistake_wake()
    test_advising_motivation_entertainment()
    test_frustration_soft_adjust()
    test_teachback_phases()
    test_mistake_catch_hint_and_ramp()
    test_walkthrough_phases()
    test_mastery_updates()
    test_plan_turn_walkthrough_and_mastery_path()
    test_extract_topic()
    test_signal_collection_is_cheap()
    print("all tool/mode tests passed")
