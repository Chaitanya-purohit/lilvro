"""Cohesion + unit checks for the andy-agent stack."""

from agent import AgentRuntime, plan_turn, respond
from contracts import Mode, Phase, Tool
from mastery import MasteryBook
from modes import MistakeState, TeachbackState, guide_for_decision, guide_mistake, guide_teachback, guide_walkthrough
from persona import flavor_for_tool, local_fallback, persona_base_prompt
from tools import SessionState, collect_signals, extract_topic, route_turn


def test_contracts_are_shared():
    from contracts import Tool as CTool
    from tools import Tool as TTool

    assert CTool is TTool
    assert flavor_for_tool(Tool.TEACHING)
    assert local_fallback("distress_signal")
    assert persona_base_prompt().startswith("You are lilvro")


def test_mental_health_overrides():
    decision = route_turn("I'm overwhelmed and I can't breathe")
    assert decision.primary_tool == Tool.MENTAL_HEALTH
    assert decision.adjust is True


def test_distress_and_off_topic_are_local():
    distress = respond("I feel hopeless and want to disappear", runtime=AgentRuntime.fresh())
    assert distress.local_only is True
    assert "trusted adult" in distress.text.lower()
    off = respond("can we talk about fortnite instead", runtime=AgentRuntime.fresh())
    assert off.local_only is True


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
    assert route_turn("quiz me and make me catch the mistake").mode == Mode.MISTAKE


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
    assert first.phase == Phase.LISTEN
    second = guide_teachback("it's like stuff that pulls things", state)
    assert second.phase == Phase.INTENTIONAL_MISS
    assert state.gaps
    third = guide_teachback(
        "gravity is a force that pulls objects together because of mass, "
        "like earth pulling an apple down",
        state,
    )
    assert third.phase == Phase.CONCEPT_CHECK


def test_mistake_catch_and_ramp():
    state = MistakeState()
    plant = guide_mistake("quiz me about fractions", state)
    assert plant.phase == Phase.PLANT_MISTAKE
    assert state.topic == "fractions"
    caught = guide_mistake("actually that's wrong, it should be squared", state)
    assert caught.phase == Phase.CAUGHT
    again = guide_mistake("another one", state)
    assert again.phase == Phase.PLANT_MISTAKE


def test_walkthrough_phases():
    session = SessionState()
    assert guide_walkthrough("help me with fractions", session).phase == Phase.ORIENT
    session.turns = 3
    session.topic = "fractions"
    session.frustration_streak = 2
    assert guide_walkthrough("I don't get it", session).phase == Phase.STUCK


def test_guide_for_decision_dispatcher():
    session = SessionState()
    teachback = TeachbackState()
    mistake = MistakeState()
    decision = route_turn("let me teach you about atoms", session)
    guidance = guide_for_decision(
        "let me teach you about atoms",
        decision=decision,
        session=session,
        teachback=teachback,
        mistake=mistake,
    )
    assert guidance.mode == Mode.TEACHBACK
    assert guidance.phase == Phase.LISTEN
    assert teachback.active is True


def test_mastery_from_guidance():
    book = MasteryBook()
    from contracts import ModeGuidance

    score = book.note_from_guidance(
        topic="fractions",
        guidance=ModeGuidance(Mode.MISTAKE, Phase.CAUGHT, "ok"),
        engagement=False,
    )
    assert score > 0.35
    assert "fractions" in book.coaching_line("fractions")


def test_runtime_turn_plan_only():
    runtime = AgentRuntime.fresh()
    planned = runtime.turn("walk me through the integral of x", plan_only=True)
    assert planned.decision.primary_tool == Tool.TEACHING
    assert planned.guidance.phase in {Phase.ORIENT, Phase.STEP, Phase.CHECK}
    assert runtime.session.turns == 1
    assert "mastery" in runtime.snapshot()


def test_signals_passed_once_in_plan_turn():
    runtime = AgentRuntime.fresh()
    planned, runtime = plan_turn("help me with photosynthesis", runtime)
    assert planned.decision.topic == "photosynthesis"
    assert runtime.session.topic == "photosynthesis"


def test_extract_topic_and_signals():
    assert extract_topic("let me teach you about derivatives") == "derivatives"
    assert extract_topic("quiz me about gravity") == "gravity"
    signals = collect_signals("I give up, this is stupid")
    assert signals.frustration >= 1
    assert signals.is_frustrated is True


if __name__ == "__main__":
    test_contracts_are_shared()
    test_mental_health_overrides()
    test_distress_and_off_topic_are_local()
    test_teachback_wake_topic_and_sticky()
    test_mistake_wake()
    test_advising_motivation_entertainment()
    test_frustration_soft_adjust()
    test_teachback_phases()
    test_mistake_catch_and_ramp()
    test_walkthrough_phases()
    test_guide_for_decision_dispatcher()
    test_mastery_from_guidance()
    test_runtime_turn_plan_only()
    test_signals_passed_once_in_plan_turn()
    test_extract_topic_and_signals()
    print("all andy-agent cohesion tests passed")
