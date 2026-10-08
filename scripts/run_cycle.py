#!/usr/bin/env python3
"""
Orquestador de los dos flujos del ciclo.

Reemplaza a run_daily.py, que era el reporte de solo lectura del fondo simulado.

Por que dos flujos y no uno: el ciclo anterior hacia todo junto — portafolio,
candidatos, fundamentals y tesis — y tardaba de 10 a 60 minutos. El del 7-oct murio
a los 61 minutos por timeout. Separar el barrido del analisis hace que ninguna
corrida tenga que hacer todo.

    barrido (diario)
        Rapido y barato. Revisa el portafolio, mira si la watchlist llego a precio,
        y encola candidatos. No escribe tesis.

    reporte (lun/mie)
        Consume 2-3 de la cola y los analiza a fondo con las tres etapas. Este es el
        que produce recomendaciones.

Este script prepara el contexto; el analisis en si lo hace Ataraxia leyendo
src/agent/prompt.py. No es un reemplazo del agente — es lo que le deja la mesa puesta.

Uso:
    python scripts/run_cycle.py barrido
    python scripts/run_cycle.py reporte
    python scripts/run_cycle.py reporte --take 3
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.data.portfolio_csv import load_snapshot  # noqa: E402
from src.db import carlson as k  # noqa: E402
from src.db import models as db  # noqa: E402

PY = str(REPO / "venv" / "bin" / "python")


def _run(script: str, *args: str) -> None:
    """Corre un script del repo y deja que su salida fluya."""
    subprocess.run([PY, str(REPO / "scripts" / script), *args], check=True, timeout=90)


def _header(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def barrido(args: argparse.Namespace) -> int:
    """Flujo diario: estado, precios de la watchlist, y encolar. Sin tesis."""
    _header("BARRIDO DIARIO")

    flushed = 0 if args.dry_run else db.flush_pending_writes()
    if flushed:
        print(f"Reenviadas {flushed} escritura(s) que habian quedado pendientes.\n")

    _header("1. Portafolio")
    _run("brain_portfolio.py")

    _header("2. Watchlist — ¿alguna llego a precio?")
    _run("brain_watchlist.py", "--check-prices")

    _header("3. Encolar candidatos")
    if args.dry_run:
        print("[dry-run] No se encola ni avanza la rotacion; se muestra la cola existente.")
        _run("brain_candidates.py", "--show")
    else:
        _run("brain_candidates.py", "--batch-size", str(args.batch_size))

    _header("Cierre del barrido")
    pend = k.get_queue(limit=200)
    print(f"Cola pendiente: {len(pend)} candidato(s)")
    print("\nEl barrido no escribe tesis. El analisis profundo corre en el reporte")
    print("de lun/mie, que consume esta cola de a 2-3.")
    return 0


def reporte(args: argparse.Namespace) -> int:
    """Flujo de lun/mie: toma 2-3 de la cola para analisis profundo."""
    _header("REPORTE — contexto para el analisis")

    flushed = 0 if args.dry_run else db.flush_pending_writes()
    if flushed:
        print(f"Reenviadas {flushed} escritura(s) pendientes.\n")

    _header("1. Portafolio")
    _run("brain_portfolio.py")

    try:
        s = load_snapshot()
        if s.is_stale:
            print(f"\n*** El CSV tiene {s.age_days} dias. Decilo explicitamente en el")
            print("    reporte y pedile a LP un export nuevo. ***")
    except FileNotFoundError:
        print("\n*** No hay CSV de portafolio. Pedirselo a LP antes de opinar. ***")

    _header("2. Watchlist")
    _run("brain_watchlist.py", "--check-prices")

    _header("3. Recomendaciones esperando decision de LP")
    _run("log_recommendation.py", "list", "--pending")

    _header(f"4. Candidatos para analizar a fondo (hasta {args.take})")
    queue = k.get_queue(limit=args.take)
    if not queue:
        print("Cola vacia. Corre el barrido primero:")
        print("  python scripts/run_cycle.py barrido")
        return 0

    for c in queue:
        print(f"\n  {c['ticker']}  [prioridad {c['priority']} · {c['source']}]")
        print(f"      {c['reason']}")

    tickers = [c["ticker"] for c in queue]
    print(f"\n{'=' * 70}")
    print("A analizar en este ciclo:", ", ".join(tickers))
    print(f"{'=' * 70}")
    print("""
Framework (src/agent/prompt.py) — las etapas son filtros, no secciones de informe:

  Paso previo   Verificar que negocio es HOY. Un ticker no cambia cuando la
                empresa si.

  Etapa 1       Riesgo y foso durable. ELIMINATORIA.
                Anatomia (tipo + el numero que lo prueba), durabilidad como
                derivada (ROIC y margen bruto a 5-10 años), ROIC vs WACC,
                caso del atacante con nombre propio, verificacion por segmento.
                Si falla: dos lineas con el motivo y se descarta. No avanza.

  Etapa 2       Checklist Carlson — basics y balance.

  Etapa 3       Valuacion: P/S contra pares + TAM. De aqui salen precio
                objetivo y momento de compra.

Salidas posibles:
  compra              pasa las tres y el precio lo vale HOY
  agregar_watchlist   pasa negocio, falla solo precio
  descartar           falla el negocio
  esperar_precio      ya esta en watchlist, sigue cara

Datos:
  venv/bin/python scripts/brain_fundamentals.py TICKER

Registrar:
  venv/bin/python scripts/log_recommendation.py add TICKER --verdict V --rationale "..."
  venv/bin/python scripts/brain_watchlist.py --add TICKER --thesis "..." --trigger "..."
""")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("barrido", help="Flujo diario: estado y encolar")
    p.add_argument("--batch-size", type=int, default=6)
    p.set_defaults(func=barrido)

    p = sub.add_parser("reporte", help="Flujo lun/mie: analisis profundo")
    p.add_argument("--take", type=int, default=3,
                   help="Cuantos candidatos tomar de la cola (default 3)")
    p.set_defaults(func=reporte)

    for command_parser in sub.choices.values():
        command_parser.add_argument("--dry-run", action="store_true", help="Solo lectura: sin flush, encolado ni registro")
    args = ap.parse_args()
    if args.dry_run:
        os.environ["ATARAXIA_DRY_RUN"] = "1"
        print("[dry-run] Contexto solamente. Sin analisis LLM, mensajes ni escrituras.", flush=True)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
