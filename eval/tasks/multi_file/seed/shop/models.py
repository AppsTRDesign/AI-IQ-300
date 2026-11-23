from dataclasses import dataclass


@dataclass
class Product:
    name: str
    price: float
    qty: int = 0

    def value(self) -> float:
        return self.price * self.qty
