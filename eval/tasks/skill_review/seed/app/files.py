"""Sends back files that users uploaded earlier."""
import os

UPLOADS = "uploads"


def read_upload(filename):
    path = os.path.join(UPLOADS, filename)
    with open(path, "rb") as f:
        return f.read()
