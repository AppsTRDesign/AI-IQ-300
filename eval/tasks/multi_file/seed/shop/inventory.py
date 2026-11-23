from .models import Product


class Inventory:
    def __init__(self):
        self.items: dict[str, Product] = {}

    def add(self, name: str, price: float, qty: int = 0) -> Product:
        p = self.items.get(name)
        if p:
            p.qty += qty
            p.price = price
        else:
            p = self.items[name] = Product(name, price, qty)
        return p

    def total(self) -> float:
        return round(sum(p.value() for p in self.items.values()), 2)

    def cheapest(self) -> Product | None:
        return min(self.items.values(), key=lambda p: p.price, default=None)
