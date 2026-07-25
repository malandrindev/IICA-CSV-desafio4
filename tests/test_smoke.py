"""Teste mínimo da estrutura importável do pacote."""

import sys
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import iica_csv  # noqa: E402


def test_package_has_version() -> None:
    assert iica_csv.__version__
