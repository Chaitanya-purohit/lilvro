import unittest

from guardrail import GuardrailCategory, check_message, check_message_with_ai, check_message_with_openai


class GuardrailTests(unittest.TestCase):
    def test_stem_question_is_allowed(self) -> None:
        result = check_message("What is the square root of 25?")
        self.assertTrue(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.ALLOWED)
        self.assertEqual(result.response, "")

    def test_off_topic_request_is_redirected(self) -> None:
        result = check_message("Can you play Minecraft with me?")
        self.assertFalse(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.OFF_TOPIC)
        self.assertIn("math", result.response.lower())

    def test_personal_data_request_is_refused(self) -> None:
        result = check_message("What is your address?")
        self.assertFalse(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.PERSONAL_DATA)
        self.assertIn("personal information", result.response.lower())

    def test_distress_message_redirects_to_trusted_adult(self) -> None:
        result = check_message("I want to hurt myself.")
        self.assertFalse(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.MENTAL_HEALTH)
        self.assertIn("trusted adult", result.response.lower())

    def test_internet_request_is_refused(self) -> None:
        result = check_message("Search the internet for this.")
        self.assertFalse(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.INTERNET_REQUEST)
        self.assertIn("can't browse", result.response.lower())

    def test_unknown_topic_is_redirected(self) -> None:
        result = check_message("Tell me a joke.")
        self.assertFalse(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.OFF_TOPIC)

    def test_ai_can_allow_an_unusual_stem_question(self) -> None:
        prompts = []

        def classifier(prompt: str) -> dict[str, object]:
            prompts.append(prompt)
            return {"category": "allowed", "confidence": 0.96}

        result = check_message_with_ai("Why do leaves change color?", classifier)

        self.assertTrue(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.ALLOWED)
        self.assertIn("exactly these keys", prompts[0])

    def test_ai_low_confidence_fails_closed(self) -> None:
        result = check_message_with_ai(
            "Tell me something interesting.",
            lambda _: {"category": "allowed", "confidence": 0.40},
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.UNCERTAIN)

    def test_ai_never_overrides_deterministic_distress_rule(self) -> None:
        classifier_called = False

        def classifier(_: str) -> dict[str, object]:
            nonlocal classifier_called
            classifier_called = True
            return {"category": "allowed", "confidence": 1.0}

        result = check_message_with_ai("I want to hurt myself.", classifier)

        self.assertEqual(result.category, GuardrailCategory.MENTAL_HEALTH)
        self.assertFalse(classifier_called)

    def test_invalid_ai_result_fails_closed(self) -> None:
        result = check_message_with_ai("Tell me something interesting.", lambda _: "not json")

        self.assertFalse(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.UNCERTAIN)

    def test_openai_adapter_without_key_fails_closed(self) -> None:
        result = check_message_with_openai("Tell me something interesting.")

        self.assertFalse(result.allowed)
        self.assertEqual(result.category, GuardrailCategory.UNCERTAIN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
