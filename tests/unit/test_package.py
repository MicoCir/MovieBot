# tests/unit/test_package.py
import importlib


def test_import_moviebot():
    package = importlib.import_module("moviebot")

    assert package.__name__ == "moviebot"
