#!/usr/bin/env python3
"""
La bitacora: que recomendo Ataraxia y que acciono LP.

Reemplaza a log_manual_trade.py, que registraba fills contra la DB del fondo simulado.
Ahora el portafolio real vive en el CSV de Schwab, asi que lo que hace falta registrar
no son las posiciones (ya estan en el CSV) sino la **decision**: que se recomendo, con
que razonamiento, y que hizo LP con eso.

La brecha entre lo recomendado y lo ejecutado es informacion util. Si LP rechaza
sistematicamente cierto tipo de recomendacion, eso dice algo del criterio — de Ataraxia
o de LP, y en cualquier caso vale saberlo.

Uso:
    # Ataraxia registra una recomendacion (normalmente desde el ciclo, no a mano)
    python scripts/log_recommendation.py add TICKER --verdict compra \\
        --rationale "..." [--price 100 --target 120 --size 4 \\
        --bear "..." --bear-prob 0.25 --stage1 pasa --stage2 pasa]

    # LP registra que hizo
    python scripts/log_recommendation.py action ID --did ejecutada --price 98.50
    python scripts/log_recommendation.py action ID --did rechazada --notes "no me convencio"

    # Ver
    python scripts/log_recommendation.py list
    python scripts/log_recommendation.py list --pending
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import carlson as k  # noqa: E402

VERDICTS = ["compra", "agregar_watchlist", "esperar_precio", "descartar",
            "recortar", "vender", "mantener"]
ACTIONS = ["ejecutada", "rechazada", "parcial", "pendiente"]


def cmd_add(a: argparse.Namespace) -> int:
    k.log_recommendation(
        a.ticker,
        verdict=a.verdict,
        rationale=a.rationale,
        stage1_moat=a.stage1_moat,
        stage1_verdict=a.stage1,
        stage2_checklist=a.stage2_checklist,
        stage2_verdict=a.stage2,
        stage3_valuation=a.stage3,
        price_at_recommendation=a.price,
        target_price=a.target,
        proposed_size_pct=a.size,
        bear_case=a.bear,
        bear_case_probability=a.bear_prob,
    )
    print(f"Registrada: {a.ticker.upper()} — {a.verdict}")
    if a.verdict in ("compra", "recortar", "vender"):
        print("Queda pendiente de accion de LP.")
    return 0


def cmd_action(a: argparse.Namespace) -> int:
    k.record_lp_action(a.id, a.did, executed_price=a.price, notes=a.notes)
    print(f"Recomendacion #{a.id}: {a.did}")
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    rows = k.get_recommendations(limit=a.limit, pending_only=a.pending)
    if not rows:
        print("Sin recomendaciones pendientes." if a.pending else "Bitacora vacia.")
        return 0

    title = "Pendientes de accion" if a.pending else "Bitacora"
    print(f"{title} — {len(rows)} entrada(s)\n")

    for r in rows:
        head = f"  #{r['id']}  {r['date']}  {r['ticker']:6} {r['verdict'].upper()}"
        if r.get("lp_action"):
            head += f"  -> LP: {r['lp_action']}"
        print(head)

        bits = []
        if r.get("price_at_recommendation") is not None:
            bits.append(f"precio ${float(r['price_at_recommendation']):,.2f}")
        if r.get("target_price") is not None:
            bits.append(f"objetivo ${float(r['target_price']):,.2f}")
        if r.get("proposed_size_pct") is not None:
            bits.append(f"tamaño {float(r['proposed_size_pct']):.1f}%")
        if bits:
            print(f"        {' | '.join(bits)}")

        etapas = [f"E{i}:{r.get(f'stage{i}_verdict')}" for i in (1, 2)
                  if r.get(f"stage{i}_verdict")]
        if etapas:
            print(f"        {' '.join(etapas)}")

        print(f"        {r['rationale'][:140]}")
        if r.get("bear_case"):
            prob = r.get("bear_case_probability")
            p = f" ({float(prob):.0%})" if prob is not None else ""
            print(f"        bear{p}: {r['bear_case'][:120]}")
        if r.get("lp_executed_price") is not None:
            print(f"        ejecutada a ${float(r['lp_executed_price']):,.2f}")
        if r.get("lp_notes"):
            print(f"        nota LP: {r['lp_notes']}")
        print()

    if a.pending:
        print("Registrar que hiciste:")
        print("  python scripts/log_recommendation.py action ID --did ejecutada --price X")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="Registra una recomendacion de Ataraxia")
    p.add_argument("ticker")
    p.add_argument("--verdict", required=True, choices=VERDICTS)
    p.add_argument("--rationale", required=True)
    p.add_argument("--price", type=float, help="Precio al momento del analisis")
    p.add_argument("--target", type=float, help="Precio objetivo")
    p.add_argument("--size", type=float, help="%% de cartera propuesto")
    p.add_argument("--bear", help="Bear case")
    p.add_argument("--bear-prob", type=float, help="Probabilidad del bear case (0-1)")
    p.add_argument("--stage1", choices=["pasa", "falla"], help="Veredicto Etapa 1")
    p.add_argument("--stage1-moat", help="Resumen del foso")
    p.add_argument("--stage2", choices=["pasa", "falla"], help="Veredicto Etapa 2")
    p.add_argument("--stage2-checklist", help="Resumen del checklist")
    p.add_argument("--stage3", help="Resumen de valuacion")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("action", help="LP registra que hizo con una recomendacion")
    p.add_argument("id", type=int)
    p.add_argument("--did", required=True, choices=ACTIONS)
    p.add_argument("--price", type=float, help="Precio al que ejecutaste")
    p.add_argument("--notes")
    p.set_defaults(func=cmd_action)

    p = sub.add_parser("list", help="Ver la bitacora")
    p.add_argument("--pending", action="store_true", help="Solo las que esperan accion de LP")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
