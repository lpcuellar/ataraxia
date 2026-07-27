#!/usr/bin/env python3
"""
Entry point del scheduler diario de Ataraxia.

Uso previsto (Fase 5):
    python scripts/run_daily.py            # corrida normal
    python scripts/run_daily.py --dry-run  # sin ejecutar ordenes, solo para probar

Programar via cron en la maquina local (ver PROJECT_PLAN.md Seccion 6 sobre el riesgo
operacional de hosting local y como mitigarlo).

Stub — depende de que agent/loop.py este implementado (Fase 2/3).
"""

import argparse

from src.agent.loop import run_daily_cycle


def main():
    parser = argparse.ArgumentParser(description="Corrida diaria de Ataraxia")
    parser.add_argument("--dry-run", action="store_true",
                         help="Corre el ciclo sin ejecutar ordenes reales")
    args = parser.parse_args()

    if args.dry_run:
        print("Modo dry-run: no se ejecutaran ordenes.")

    run_daily_cycle()


if __name__ == "__main__":
    main()
