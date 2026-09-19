import unittest

from math_renderer import render_math


class MathRendererTests(unittest.TestCase):
    def test_square_root(self) -> None:
        self.assertEqual(render_math(r"\sqrt{25}"), "the square root of 25")

    def test_squared_and_cubed(self) -> None:
        self.assertEqual(render_math("x^2"), "x squared")
        self.assertEqual(render_math("3^3"), "3 cubed")

    def test_fraction(self) -> None:
        self.assertEqual(render_math(r"\frac{1}{2}"), "the fraction 1 over 2")

    def test_basic_operators(self) -> None:
        self.assertEqual(render_math("4 * 3 = 12"), "4 times 3 equals 12")
        self.assertEqual(render_math("8 / 2 = 4"), "8 divided by 2 equals 4")

    def test_shared_symbol_file(self) -> None:
        self.assertEqual(render_math(r"\pi"), "pi")
        self.assertEqual(render_math(r"A \subseteq B"), "A is a subset of B")

    def test_factorial_and_prose_punctuation(self) -> None:
        self.assertEqual(render_math("5!"), "5 factorial")
        self.assertEqual(render_math("Great!"), "Great!")

    def test_markdown_asterisks_are_not_multiplication(self) -> None:
        self.assertEqual(render_math("Use *bold* text."), "Use bold text.")

    def test_codex_style_explanation(self) -> None:
        response = r"To solve x^2 = 9, take the square root: x = \sqrt{9} = 3."
        expected = "To solve x squared equals 9, take the square root: x equals the square root of 9 equals 3."
        self.assertEqual(render_math(response), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
