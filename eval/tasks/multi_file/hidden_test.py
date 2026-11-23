"""Hidden checks of the multi-file change (the model never sees this file). Run with the workspace on sys.path."""
import subprocess
import sys

import pytest

from shop.cli import demo
from shop.inventory import Inventory
from shop.models import Product
from shop.pricing import discounted, with_tax
from shop.report import render


def test_unit_price_field():
    p = Product("x", unit_price=2.0, qty=3)
    assert p.unit_price == 2.0 and p.value() == 6.0
    assert not hasattr(p, "price")


def test_inventory_and_pricing_still_work():
    inv = Inventory()
    inv.add("a", 1.5, 2)
    inv.add("b", 0.5, 10)
    inv.add("a", 2.0, 1)
    assert inv.items["a"].unit_price == 2.0 and inv.items["a"].qty == 3
    assert inv.total() == 11.0
    assert inv.cheapest().name == "b"
    assert discounted(inv.items["a"], 50) == 1.0 and with_tax(inv.items["b"], 0.1) == 0.55


def test_low_stock():
    inv = demo()
    low = inv.low_stock()
    assert sorted(p.name for p in low) == ["bread", "milk"]
    assert [p.name for p in inv.low_stock(limit=20)] and {p.name for p in inv.low_stock(limit=20)} == {"bread", "cheese", "milk"}


def test_report_shows_low_stock():
    out = render(demo())
    assert "TOTAL" in out
    tail = out.lower()
    assert "low" in tail or "düşük" in tail or "az" in tail
    assert "bread" in out and "milk" in out


def test_cli_runs():
    r = subprocess.run([sys.executable, "-m", "shop.cli"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-500:]
    assert "cheapest" in r.stdout
