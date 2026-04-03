"""
Calculator module providing basic arithmetic operations.

This module contains functions for performing addition, subtraction,
multiplication, and division operations with proper error handling.
"""


def add(a, b):
    """
    Add two numbers together.

    Args:
        a: First number (int or float)
        b: Second number (int or float)

    Returns:
        The sum of a and b (int or float)

    Examples:
        >>> add(2, 3)
        5
        >>> add(2.5, 3.5)
        6.0
    """
    return a + b


def subtract(a, b):
    """
    Subtract the second number from the first number.

    Args:
        a: First number (int or float)
        b: Second number (int or float)

    Returns:
        The result of a - b (int or float)

    Examples:
        >>> subtract(5, 3)
        2
        >>> subtract(5.5, 2.5)
        3.0
    """
    return a - b


def multiply(a, b):
    """
    Multiply two numbers together.

    Args:
        a: First number (int or float)
        b: Second number (int or float)

    Returns:
        The product of a and b (int or float)

    Examples:
        >>> multiply(2, 3)
        6
        >>> multiply(2.5, 4)
        10.0
    """
    return a * b


def divide(a, b):
    """
    Divide the first number by the second number.

    Args:
        a: Dividend (int or float)
        b: Divisor (int or float)

    Returns:
        The result of a / b (float)

    Raises:
        ZeroDivisionError: If b is zero

    Examples:
        >>> divide(6, 3)
        2.0
        >>> divide(5, 2)
        2.5

    Note:
        This function handles division by zero by raising a ZeroDivisionError.
    """
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b