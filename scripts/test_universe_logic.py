#!/usr/bin/env python3
"""
Verifica la logica PURA del embudo de universo (build_quantitative_pool, select_next_batch)
con datos sinteticos — no requiere una API key de FMP ni conexion de red.

Esto NO prueba la integracion real con FMP (eso requiere una API key real, ver
scripts/smoke_test_fmp.py), pero confirma que la logica de filtrado e interseccion y la
rotacion circular funcionan correctamente antes de gastar cuota de API en probarlo en vivo.

Uso: python scripts/test_universe_logic.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.universe import build_quantitative_pool, select_next_batch


def check(label: str, condition: bool):
    status = "OK" if condition else "FALLO"
    print(f"[{status}] {label}")
    if not condition:
        global failures
        failures += 1


failures = 0

# --- Test 1: interseccion basica ---
sp500 = [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "NVDA"}, {"symbol": "TSLA"}]
screener = [{"symbol": "AAPL"}, {"symbol": "NVDA"}, {"symbol": "COST"}]  # COST no esta en sp500 mock, TSLA no paso el screener
pool = build_quantitative_pool(sp500, screener)
check("Interseccion devuelve solo lo que esta en ambas listas", pool == ["AAPL", "NVDA"])
check("Pool esta ordenado alfabeticamente", pool == sorted(pool))

# --- Test 2: interseccion vacia no revienta ---
empty_pool = build_quantitative_pool([], [])
check("Pool vacio con inputs vacios no lanza excepcion", empty_pool == [])

# --- Test 3: rotacion basica sin dar la vuelta ---
big_pool = [f"T{i}" for i in range(10)]
batch, next_idx = select_next_batch(big_pool, next_index=0, batch_size=4)
check("Primer lote toma los primeros 4", batch == ["T0", "T1", "T2", "T3"])
check("next_index avanza correctamente", next_idx == 4)

# --- Test 4: rotacion continua desde donde quedo ---
batch2, next_idx2 = select_next_batch(big_pool, next_index=next_idx, batch_size=4)
check("Segundo lote continua desde el indice anterior", batch2 == ["T4", "T5", "T6", "T7"])
check("next_index avanza de nuevo", next_idx2 == 8)

# --- Test 5: rotacion da la vuelta al final del pool (circular) ---
batch3, next_idx3 = select_next_batch(big_pool, next_index=8, batch_size=4)
check(
    "Tercer lote da la vuelta circularmente cuando se acaba el pool",
    batch3 == ["T8", "T9", "T0", "T1"],
)
check("next_index tambien da la vuelta", next_idx3 == 2)

# --- Test 6: batch_size mayor que el pool no revienta ---
small_pool = ["A", "B", "C"]
batch4, next_idx4 = select_next_batch(small_pool, next_index=0, batch_size=10)
check(
    "batch_size mayor al pool devuelve el pool completo sin duplicar",
    batch4 == ["A", "B", "C"],
)

# --- Test 7: pool vacio en select_next_batch no revienta ---
batch5, next_idx5 = select_next_batch([], next_index=0, batch_size=5)
check("Pool vacio en select_next_batch devuelve lote vacio", batch5 == [] and next_idx5 == 0)

print()
if failures == 0:
    print("Todos los tests de logica pura pasaron.")
    sys.exit(0)
else:
    print(f"{failures} test(s) fallaron.")
    sys.exit(1)
