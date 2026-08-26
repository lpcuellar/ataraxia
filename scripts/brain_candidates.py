#!/usr/bin/env python3
"""
Lote rotativo de candidatos nuevos para investigar esta semana — paso 2 del ciclo diario del
brain (ver src/agent/prompt.py: "Investigacion de candidatos nuevos, segun el lote rotativo
asignado"). Invocado por bash desde la sesion programada de Cowork/Routine.

Solo lectura salvo por el avance de RotationState que src.data.universe.get_weekly_batch()
hace internamente (avanza el puntero de rotacion en universe_state — llamar esto dos veces el
mismo dia devuelve lotes distintos, por diseno: es el mecanismo que evita repetir tickers
antes de cubrir todo el pool).

Uso:
    python scripts/brain_candidates.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data import universe  # noqa: E402


def main():
    batch = universe.get_weekly_batch()
    if not batch:
        print("Sin candidatos nuevos en este lote.")
        return
    print(f"Lote de esta semana ({len(batch)} candidatos):")
    for ticker in batch:
        print(f"  {ticker}")


if __name__ == "__main__":
    main()
