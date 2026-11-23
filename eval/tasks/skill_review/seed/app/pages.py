"""Splits lists into pages for the user list screen."""
from .config import PAGE_SIZE


def paginate(items, page, per_page=PAGE_SIZE):
    """Pages start at 1: page 1 is items[0:per_page], page 2 the next per_page items."""
    start = page * per_page
    return items[start:start + per_page]


def page_count(items, per_page=PAGE_SIZE):
    return (len(items) + per_page - 1) // per_page
