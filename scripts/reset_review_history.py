#!/usr/bin/env python3
"""
Resetea el historial de revision del universo para que las empresas vuelvan a la
rotacion bajo el framework de Carlson.

Por que: `reviewed_ever` acumulo ~250 empresas evaluadas con el framework anterior
(las seis preguntas: cuello de botella, backlog, pricing power, tailwind, retorno
modelado, bear case). Ese framework fue reemplazado por las tres etapas de Carlson,
que pesan cosas distintas — foso con evidencia numerica, durabilidad como derivada,
caso del atacante, y valuacion por P/S relativo.

Si no se resetea, Ataraxia nunca vuelve a mirar esas empresas y arrastra descartes
hechos con un criterio que ya no es el suyo. Entre esas 250 puede haber buenas
empresas descartadas por el motivo equivocado.

El pool y el indice de rotacion NO se tocan: el universo sigue siendo el mismo, solo
se limpia la marca de "ya la vi".

Guarda el historial anterior en data/reviewed_ever_pre_carlson.json antes de borrarlo.

Uso:
    python scripts/reset_review_history.py --dry-run
    python scripts/reset_review_history.py --apply
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.models import get_universe_state, save_universe_state  # noqa: E402

BACKUP = Path(__file__).resolve().parent.parent / "data" / "reviewed_ever_pre_carlson.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Muestra que haria, sin escribir")
    g.add_argument("--apply", action="store_true", help="Aplica el reset")
    args = ap.parse_args()

    state = get_universe_state()
    reviewed = list(state.get("reviewed_ever", []))
    pool = list(state.get("pool", []))

    print(f"Pool actual:          {len(pool)} tickers (no se toca)")
    print(f"next_index:           {state.get('next_index')} (no se toca)")
    print(f"reviewed_ever actual: {len(reviewed)} tickers")

    if not reviewed:
        print("\nreviewed_ever ya esta vacio — nada que hacer.")
        return 0

    print(f"\nSe limpiaria reviewed_ever y las {len(reviewed)} empresas volverian a la")
    print("rotacion para evaluarse con el framework de Carlson.")
    print(f"Respaldo: {BACKUP}")

    if args.dry_run:
        print("\n[dry-run] No se escribio nada.")
        return 0

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(
        json.dumps(
            {
                "archived_at": datetime.now().isoformat(timespec="seconds"),
                "reason": "Framework reemplazado por las tres etapas de Carlson",
                "framework": "seis preguntas (pre-Carlson)",
                "reviewed_ever": reviewed,
                "count": len(reviewed),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nRespaldo escrito: {BACKUP.name} ({len(reviewed)} tickers)")

    save_universe_state(
        pool=pool,
        next_index=state.get("next_index", 0),
        pool_last_refreshed=state.get("pool_last_refreshed"),
        reviewed_ever=[],
    )

    after = get_universe_state()
    print(f"reviewed_ever ahora: {len(after.get('reviewed_ever', []))}")
    print(f"pool intacto:        {len(after.get('pool', []))}")
    print("\nListo. El universo completo vuelve a estar disponible bajo el framework nuevo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
