from .models import Product


def discounted(p: Product, percent: float) -> float:
    """The product's price after a discount of `percent` (0-100)."""
    return round(p.price * (1 - percent / 100), 2)


def with_tax(p: Product, rate: float = 0.20) -> float:
    return round(p.price * (1 + rate), 2)
