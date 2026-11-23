from .inventory import Inventory


def render(inv: Inventory) -> str:
    lines = ["INVENTORY"]
    for p in sorted(inv.items.values(), key=lambda p: p.name):
        lines.append(f"{p.name:<12} {p.qty:>4} x {p.price:>8.2f}")
    lines.append(f"TOTAL {inv.total():.2f}")
    return "\n".join(lines)
