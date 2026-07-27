#!/usr/bin/env python3
"""
Smoke test CON red real — confirma que tu API key de FMP funciona y que el pipeline completo
(fundamentales, mercado, embudo de universo) corre de punta a punta contra la API real.

Requiere una FMP_API_KEY real en .env. La logica pura ya esta verificada por separado en
test_universe_logic.py (sin necesitar red) — este script prueba la integracion, no la logica.

Uso: python scripts/smoke_test_fmp.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data import fundamentals, market, universe


def run():
    print("1. Probando get_key_metrics('AAPL')...")
    metrics = fundamentals.get_key_metrics("AAPL")
    assert metrics, "get_key_metrics devolvio vacio — revisa la API key"
    print(f"   OK — {len(metrics)} campos recibidos")

    print("2. Probando get_ratios('AAPL')...")
    ratios = fundamentals.get_ratios("AAPL")
    assert ratios, "get_ratios devolvio vacio"
    print(f"   OK — {len(ratios)} campos recibidos")

    print("3. Probando get_analyst_estimates('AAPL')...")
    estimates = fundamentals.get_analyst_estimates("AAPL", limit=1)
    assert estimates, "get_analyst_estimates devolvio vacio"
    print(f"   OK — {len(estimates)} registro(s)")

    print("4. Probando get_sp500_constituents()...")
    constituents = fundamentals.get_sp500_constituents()
    assert len(constituents) > 400, f"esperaba ~500 constituyentes, llegaron {len(constituents)}"
    print(f"   OK — {len(constituents)} constituyentes")

    print("5. Probando screen_by_market_cap($10B)...")
    screener = fundamentals.screen_by_market_cap(10_000_000_000)
    assert screener, "el screener devolvio vacio"
    print(f"   OK — {len(screener)} acciones sobre $10B market cap")

    print("6. Probando get_price('AAPL')...")
    price = market.get_price("AAPL")
    assert price and price > 0, "get_price devolvio un valor invalido"
    print(f"   OK — AAPL @ ${price}")

    print("7. Probando el embudo completo: universe.get_weekly_batch()...")
    batch = universe.get_weekly_batch()
    assert batch, "el embudo no devolvio ningun ticker — revisa los filtros en universe.yaml"
    print(f"   OK — lote de esta semana: {batch}")

    print("\nTodo el pipeline de Fase 1 funciona de punta a punta.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"\nFALLO: {e}")
        sys.exit(1)
