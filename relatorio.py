"""Gera o PDF da eleição presidencial de 2026 em Três Rios.

Uso:
    python relatorio.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from eleicoes.relatorio import gerar


def main() -> int:
    caminho = gerar()
    print(f"PDF: {caminho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
