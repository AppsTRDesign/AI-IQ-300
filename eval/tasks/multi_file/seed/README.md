# shop

A tiny inventory demo.

- `Product(name, price, qty)`: one product; `value()` is `price * qty`.
- `Inventory.add(name, price, qty)`, `Inventory.total()`, `Inventory.cheapest()`.
- `pricing.discounted(p, percent)`, `pricing.with_tax(p, rate)`.
- `python -m shop.cli` prints the demo report.
