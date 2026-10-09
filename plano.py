"""Gera o PDF do mapa de panfletagem em Tres Rios.

Uso:
    python plano.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from eleicoes.plano import gerar_mapa


def main() -> int:
    caminho = gerar_mapa()
    print(f"PDF: {caminho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
