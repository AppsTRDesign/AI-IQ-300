"""Hidden checks of the spec in stats.py's docstring (the model never sees this file)."""
import pytest

from stats import clamp, mean, median, mode, variance


def test_median_more():
    assert median([5]) == 5
    assert median([10, 2, 8, 4, 6, 12]) == 7
    with pytest.raises(ValueError):
        median([])


def test_mode_tie_and_order():
    assert mode([3, 3, 1, 1, 2]) == 1
    assert mode(["b", "a", "b"]) == "b"


def test_variance_more():
    assert variance([1, 2]) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        variance([1])


def test_clamp_more():
    assert clamp(11, 0, 10) == 10
    assert clamp(0.5, 0, 1) == 0.5


def test_mean_floats():
    assert mean([0.1, 0.2, 0.3]) == pytest.approx(0.2)
