import unittest

from calculator import calculate, evaluate_expression, format_result


class TestCalculator(unittest.TestCase):
    def test_basic_addition(self):
        self.assertEqual(calculate(2, "+", 3), 5)

    def test_power(self):
        self.assertEqual(calculate(2, "**", 3), 8)

    def test_floor_division(self):
        self.assertEqual(calculate(7, "//", 2), 3)

    def test_zero_division(self):
        with self.assertRaises(ZeroDivisionError):
            calculate(10, "/", 0)

    def test_expression(self):
        self.assertEqual(evaluate_expression("(2 + 3) * 4"), 20)

    def test_invalid_expression(self):
        with self.assertRaises(ValueError):
            evaluate_expression("import os")

    def test_format_result(self):
        self.assertEqual(format_result(40.0), 40)


if __name__ == "__main__":
    unittest.main()
