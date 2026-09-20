"""Tests for utterance completion gating."""

import time

from utterance_gate import GateDecision, UtteranceGate, is_ready_utterance


def test_interim_never_ready():
    gate = UtteranceGate(settle_seconds=0.0)
    result = gate.feed("help me with fractions", speech_ended=False, is_interim=True)
    assert result.decision == GateDecision.WAIT


def test_final_ready_after_settle():
    gate = UtteranceGate(settle_seconds=0.2)
    t0 = 100.0
    assert gate.feed("help me with fractions", speech_ended=True, now=t0).decision == GateDecision.WAIT
    ready = gate.feed("help me with fractions", speech_ended=True, now=t0 + 0.25)
    assert ready.decision == GateDecision.READY
    assert ready.text == "help me with fractions"


def test_filler_ignored():
    gate = UtteranceGate(settle_seconds=0.0)
    result = gate.force_evaluate("um")
    assert result.decision == GateDecision.IGNORE
    assert not is_ready_utterance("uh")


def test_trailing_incomplete_waits():
    gate = UtteranceGate(settle_seconds=0.0)
    result = gate.feed("the derivative of x is and", speech_ended=True)
    assert result.decision == GateDecision.WAIT
    assert result.reason == "trailing_incomplete"


def test_commands_allowed_when_short():
    gate = UtteranceGate(settle_seconds=0.0)
    assert gate.force_evaluate("pause").decision == GateDecision.READY
    assert gate.force_evaluate("quiz mode").decision == GateDecision.READY


def test_duplicate_suppressed():
    gate = UtteranceGate(settle_seconds=0.0)
    first = gate.force_evaluate("what is gravity")
    second = gate.force_evaluate("what is gravity")
    assert first.decision == GateDecision.READY
    assert second.decision == GateDecision.IGNORE


def test_empty_ignored():
    gate = UtteranceGate(settle_seconds=0.0)
    assert gate.feed("", speech_ended=True).decision == GateDecision.IGNORE


if __name__ == "__main__":
    test_interim_never_ready()
    test_final_ready_after_settle()
    test_filler_ignored()
    test_trailing_incomplete_waits()
    test_commands_allowed_when_short()
    test_duplicate_suppressed()
    test_empty_ignored()
    print("all utterance_gate tests passed")
