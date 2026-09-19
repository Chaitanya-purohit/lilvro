import unittest

from mood import (
	MoodAction,
	MoodState,
	choose_response_strategy,
	choose_response_strategy_with_ai,
	detect_mood,
	response_for_mood,
)


class MoodTests(unittest.TestCase):
	def test_detects_frustration(self) -> None:
		self.assertEqual(detect_mood("This is too hard."), MoodState.FRUSTRATED)

	def test_detects_disengagement(self) -> None:
		self.assertEqual(detect_mood("This is boring."), MoodState.DISENGAGED)

	def test_detects_confusion(self) -> None:
		self.assertEqual(detect_mood("How did you get that?"), MoodState.CONFUSED)

	def test_detects_confidence(self) -> None:
		self.assertEqual(detect_mood("I got it!"), MoodState.CONFIDENT)

	def test_unknown_text_is_neutral(self) -> None:
		self.assertEqual(detect_mood("What is the square root of 25?"), MoodState.NEUTRAL)

	def test_policies_match_requested_behavior(self) -> None:
		self.assertEqual(response_for_mood("frustrated").action, MoodAction.SIMPLIFY)
		self.assertEqual(response_for_mood("disengaged").action, MoodAction.REFRAME)
		self.assertEqual(response_for_mood("confused").action, MoodAction.BACKTRACK)
		self.assertEqual(response_for_mood("confident").action, MoodAction.EXTEND)

	def test_strategy_contains_tutor_instructions(self) -> None:
		strategy = choose_response_strategy("I don't get it.")
		self.assertEqual(strategy.state, MoodState.FRUSTRATED)
		self.assertIn("one idea at a time", strategy.instructions)

	def test_ai_can_detect_an_ambiguous_mood(self) -> None:
		strategy = choose_response_strategy_with_ai(
			"I guess I could try one more problem.",
			lambda _: {"mood": "confident", "confidence": 0.91},
		)

		self.assertEqual(strategy.state, MoodState.CONFIDENT)

	def test_low_confidence_mood_falls_back_to_neutral(self) -> None:
		strategy = choose_response_strategy_with_ai(
			"I guess I could try one more problem.",
			lambda _: {"mood": "confident", "confidence": 0.40},
		)

		self.assertEqual(strategy.state, MoodState.NEUTRAL)


if __name__ == "__main__":
	unittest.main(verbosity=2)
