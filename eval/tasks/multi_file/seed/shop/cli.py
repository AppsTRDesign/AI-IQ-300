"""python -m shop.cli : a demo inventory and its report."""
from .inventory import Inventory
from .pricing import discounted
from .report import render


def demo() -> Inventory:
    inv = Inventory()
    inv.add("apple", 0.5, 40)
    inv.add("bread", 2.25, 3)
    inv.add("cheese", 7.8, 12)
    inv.add("milk", 1.1, 2)
    return inv


def main() -> None:
    inv = demo()
    print(render(inv))
    p = inv.cheapest()
    print(f"cheapest: {p.name} {p.price:.2f} (-10%: {discounted(p, 10):.2f})")


if __name__ == "__main__":
    main()
