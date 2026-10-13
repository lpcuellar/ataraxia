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

# Verdicts que requieren análisis completo. Para los demás (descartar, mantener, etc.)
# los campos de análisis son opcionales.
_VERDICTS_REQUIRE_ANALYSIS = {"compra", "agregar_watchlist", "recortar"}

# Longitudes mínimas por campo — suficientes para detectar placeholders vacíos
_MIN_LENGTHS = {
    "stage1_moat": 80,       # "foso de costos de cambio; NRR 112% (Q3 2025)"
    "stage2_checklist": 80,  # "basics: pasan calidad, liderazgo, oportunidad. balance: ..."
    "stage3_valuation": 80,  # "P/S 8.2x vs peers 12.4x; objetivo $245 en 18 meses"
    "rationale": 200,        # la tesis completa
    "bear_case": 60,         # "competidor X entra con precio 30% menor"
}


def _validate_add(a: argparse.Namespace) -> list[str]:
    """Valida campos obligatorios para verdicts que requieren análisis completo.
    Devuelve lista de errores (vacía si todo está bien)."""
    if a.verdict not in _VERDICTS_REQUIRE_ANALYSIS:
        return []

    errors = []

    # Campos obligatorios para compra / agregar_watchlist
    required_fields = {
        "stage1_moat": (a.stage1_moat, "--stage1-moat"),
        "stage2_checklist": (a.stage2_checklist, "--stage2-checklist"),
        "stage3_valuation": (a.stage3, "--stage3"),
        "rationale": (a.rationale, "--rationale"),
        "bear_case": (a.bear, "--bear"),
    }
    for field, (value, flag) in required_fields.items():
        if not value:
            errors.append(f"{flag} es obligatorio para veredicto '{a.verdict}'")
        elif len(value.strip()) < _MIN_LENGTHS[field]:
            errors.append(
                f"{flag} tiene {len(value.strip())} caracteres — mínimo {_MIN_LENGTHS[field]}. "
                f"No es un placeholder: debe contener evidencia real."
            )

    # Precio objetivo obligatorio para compra
    if a.verdict == "compra" and a.target is None:
        errors.append("--target (precio objetivo) es obligatorio para veredicto 'compra'")

    # WACC obligatorio para compra (va embebido en stage3 o como flag aparte)
    if a.verdict == "compra" and a.wacc is None:
        errors.append(
            "--wacc es obligatorio para veredicto 'compra'. "
            "Es el número que permite comparar con ROIC. Estimarlo es parte del análisis."
        )

    # Bear case probability obligatorio para compra
    if a.verdict in ("compra",) and a.bear_prob is None:
        errors.append("--bear-prob es obligatorio para veredicto 'compra' (probabilidad 0.0-1.0)")

    return errors


def cmd_add(a: argparse.Namespace) -> int:
    errors = _validate_add(a)
    if errors:
        print(f"RECHAZADO — el análisis de '{a.ticker.upper()}' está incompleto:", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        print(file=sys.stderr)
        print("Una recomendación de compra sin evidencia completa no sirve para tomar", file=sys.stderr)
        print("decisiones. Completá el análisis antes de registrarlo.", file=sys.stderr)
        return 1

    # Embeber WACC en stage3_valuation si se pasó como flag separado
    stage3 = a.stage3
    if a.wacc is not None and stage3:
        wacc_pct = f"{a.wacc * 100:.1f}%"
        if "wacc" not in stage3.lower():
            stage3 = f"[WACC estimado: {wacc_pct}] {stage3}"

    # Embeber quality_flag_response en rationale si se pasó
    rationale = a.rationale
    if a.quality_flag_response:
        rationale = f"{rationale}\n\nCalidad de datos — respuesta a flags: {a.quality_flag_response}"

    k.log_recommendation(
        a.ticker,
        verdict=a.verdict,
        rationale=rationale,
        stage1_moat=a.stage1_moat,
        stage1_verdict=a.stage1,
        stage2_checklist=a.stage2_checklist,
        stage2_verdict=a.stage2,
        stage3_valuation=stage3,
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
    p.add_argument("--stage1-moat", help="Resumen del foso con evidencia numérica")
    p.add_argument("--stage2", choices=["pasa", "falla"], help="Veredicto Etapa 2")
    p.add_argument("--stage2-checklist", help="Resumen del checklist con items que pasan/fallan")
    p.add_argument("--stage3", dest="stage3", help="Resumen de valuación: P/S vs pares, precio objetivo, timing")
    p.add_argument("--wacc", type=float,
                   help="WACC estimado (0.09 = 9%%). Obligatorio para 'compra'. "
                        "Se compara con ROIC del data package para validar el foso.")
    p.add_argument("--quality-flag-response", dest="quality_flag_response",
                   help="Respuesta a cada quality_flag del data package: "
                        "cómo afectan (o no) la tesis. Obligatorio si el paquete tiene flags.")
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
