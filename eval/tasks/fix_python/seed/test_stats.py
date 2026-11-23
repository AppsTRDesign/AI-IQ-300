import pytest

from stats import clamp, mean, median, mode, variance


def test_mean():
    assert mean([1, 2, 3, 4]) == 2.5
    with pytest.raises(ValueError):
        mean([])


def test_median():
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 3, 2]) == 2.5


def test_mode():
    assert mode([1, 2, 2, 3]) == 2


def test_variance():
    assert variance([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(4.571428, rel=1e-5)


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
