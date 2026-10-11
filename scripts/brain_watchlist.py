#!/usr/bin/env python3
"""
La watchlist: empresas que pasaron el filtro de negocio pero cuyo precio todavia no
justifica la compra.

Carlson: "La mayoria de las empresas no cumpliran todas estas caracteristicas, y las que
si rara vez cotizan con descuento. Recomiendo construir una lista de empresas que cumplan
la mayoria y comprarlas cuando se presente una oportunidad decente."

Por eso la watchlist no es accesoria — es el mecanismo central. El ciclo no busca que
comprar hoy: mantiene la lista y espera el precio.

Uso:
    python scripts/brain_watchlist.py                    # ver la lista viva
    python scripts/brain_watchlist.py --check-prices     # ver cuales llegaron a precio
    python scripts/brain_watchlist.py --all              # incluye compradas y descartadas

    python scripts/brain_watchlist.py --add TICKER \\
        --thesis "..." --trigger "que tiene que pasar" --target 100 \\
        [--moat marca --evidence "..." --direction estable --attacker-prob 0.2]

    python scripts/brain_watchlist.py --close TICKER --status comprada --reason "..."
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import carlson as k  # noqa: E402

MOAT_TYPES = ["marca", "efecto_red", "costos_cambio", "ventaja_costo", "escala"]
DIRECTIONS = ["ensanchando", "estable", "erosionando"]


def _price(ticker: str) -> float | None:
    """Precio actual. Si falla, devuelve None — no rompe el listado."""
    try:
        from src.data.market import get_price

        return get_price(ticker)
    except Exception:
        return None


def show(check_prices: bool, show_all: bool) -> int:
    rows = k.get_watchlist(status=None if show_all else "esperando")
    if not rows:
        print("Watchlist vacia.")
        print("\nSe llena sola: las empresas que pasan Etapas 1 y 2 pero fallan en precio")
        print("entran aqui. Si falla el negocio se descartan, no entran.")
        return 0

    print(f"Watchlist — {len(rows)} empresa(s)\n")
    at_target = []

    for r in rows:
        tgt = float(r["target_price"]) if r["target_price"] is not None else None
        head = f"  {r['ticker']}"
        if r.get("company_name"):
            head += f" — {r['company_name']}"
        if show_all and r["status"] != "esperando":
            head += f"  [{r['status'].upper()}]"
        print(head)

        moat_bits = [b for b in (r.get("moat_type"), r.get("moat_direction")) if b]
        if moat_bits:
            print(f"      foso: {' / '.join(moat_bits)}", end="")
            if r.get("attacker_probability") is not None:
                print(f" | atacante {float(r['attacker_probability']):.0%}", end="")
            print()
        if r.get("moat_evidence"):
            print(f"      evidencia: {r['moat_evidence']}")

        print(f"      tesis: {r['thesis_summary']}")
        print(f"      gatillo: {r['what_needs_to_happen']}")

        if tgt is not None:
            line = f"      objetivo: ${tgt:,.2f}"
            if check_prices:
                p = _price(r["ticker"])
                if p is None:
                    line += "  (precio no disponible)"
                else:
                    gap = (p - tgt) / tgt
                    line += f" | actual ${p:,.2f} ({gap:+.1%})"
                    if p <= tgt:
                        line += "  <<< LLEGO A PRECIO"
                        at_target.append((r["ticker"], p, tgt))
            print(line)

        if r.get("last_reviewed_at"):
            print(f"      revisada: {r['last_reviewed_at']}")
        print()

    if check_prices and at_target:
        print("=" * 60)
        print("LLEGARON A PRECIO — revisar que la tesis de negocio siga intacta")
        print("antes de recomendar la compra:")
        for t, p, tgt in at_target:
            print(f"  {t}: ${p:,.2f} <= objetivo ${tgt:,.2f}")
    elif check_prices:
        print("Ninguna llego a precio todavia.")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-prices", action="store_true",
                    help="Compara contra el precio actual")
    ap.add_argument("--all", action="store_true",
                    help="Incluye compradas y descartadas")

    ap.add_argument("--add", metavar="TICKER", help="Agrega o actualiza una entrada")
    ap.add_argument("--thesis", help="Resumen de la tesis (requerido con --add)")
    ap.add_argument("--trigger", help="Que tiene que pasar para comprar (requerido con --add)")
    ap.add_argument("--target", type=float, help="Precio objetivo")
    ap.add_argument("--name", help="Nombre de la empresa")
    ap.add_argument("--moat", choices=MOAT_TYPES, help="Tipo de foso")
    ap.add_argument("--evidence", help="El numero que prueba el foso")
    ap.add_argument("--direction", choices=DIRECTIONS, help="Direccion del foso")
    ap.add_argument("--attacker", help="El caso del atacante")
    ap.add_argument("--attacker-prob", type=float, help="Probabilidad del atacante (0-1)")

    ap.add_argument("--close", metavar="TICKER", help="Saca una entrada de la lista viva")
    ap.add_argument("--status", choices=["comprada", "descartada"])
    ap.add_argument("--reason", help="Por que salio")

    args = ap.parse_args()

    if args.add:
        if not args.thesis or not args.trigger:
            ap.error("--add requiere --thesis y --trigger")
        k.add_to_watchlist(
            args.add,
            thesis_summary=args.thesis,
            what_needs_to_happen=args.trigger,
            company_name=args.name,
            moat_type=args.moat,
            moat_evidence=args.evidence,
            moat_direction=args.direction,
            attacker_case=args.attacker,
            attacker_probability=args.attacker_prob,
            target_price=args.target,
            price_at_entry=_price(args.add),
        )
        print(f"{args.add.upper()} en la watchlist.")
        return 0

    if args.close:
        if not args.status or not args.reason:
            ap.error("--close requiere --status y --reason")
        k.close_watchlist_entry(args.close, args.status, args.reason)
        print(f"{args.close.upper()} marcada como {args.status}.")
        return 0

    return show(args.check_prices, args.all)


if __name__ == "__main__":
    sys.exit(main())
