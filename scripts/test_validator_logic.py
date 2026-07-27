#!/usr/bin/env python3
"""
Tests de logica pura para src/guardrails/validator.py — sin red, sin DB. Corre con datos
sinteticos para verificar cada guardrail de forma aislada.

Uso: python scripts/test_validator_logic.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.guardrails import validator as v


def check(label: str, condition: bool):
    status = "[OK]" if condition else "[FAIL]"
    print(f"{status} {label}")
    if not condition:
        raise AssertionError(label)


def empty_portfolio(cash=100_000.0):
    return v.PortfolioState(positions=[], cash=cash)


def run():
    # --- caso base: compra valida en cartera vacia ---
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0)  # $1,000 / 15% de 100k = $15k max
    result = v.validate_trade_proposal(proposal, p)
    check("Compra valida dentro de todos los limites se aprueba", result.approved)

    # --- limite de 15% por posicion ---
    p = empty_portfolio(cash=100_000.0)
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=200, price=100.0)  # $20,000 = 20% > 15%
    result = v.validate_trade_proposal(proposal, p)
    check("Compra que excede 15% de la cartera se rechaza", not result.approved)
    check("La razon del rechazo menciona el limite", "15%" in result.reason or "maximo permitido" in result.reason)

    # --- agregar a una posicion existente tambien respeta el 15% ---
    existing = v.Position(ticker="AAPL", quantity=100, avg_cost=100.0, current_price=100.0)  # $10k de $100k = 10%
    p = v.PortfolioState(positions=[existing], cash=90_000.0)
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=60, price=100.0)  # +$6k -> $16k / $100k = 16%
    result = v.validate_trade_proposal(proposal, p)
    check("Agregar a una posicion existente tambien respeta el limite de 15%", not result.approved)

    # --- cash insuficiente ---
    p = empty_portfolio(cash=500.0)
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0)  # $1,000 > $500
    result = v.validate_trade_proposal(proposal, p)
    check("Compra sin cash suficiente se rechaza", not result.approved)

    # --- no se puede vender lo que no se tiene ---
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=10, price=100.0)
    result = v.validate_trade_proposal(proposal, p)
    check("Vender sin posicion abierta se rechaza", not result.approved)

    # --- no se puede vender mas de lo que se tiene ---
    existing = v.Position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=100.0)
    p = v.PortfolioState(positions=[existing], cash=1_000.0)
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=20, price=100.0)
    result = v.validate_trade_proposal(proposal, p)
    check("Vender mas cantidad de la que se tiene se rechaza", not result.approved)

    # --- venta valida ---
    existing = v.Position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=100.0)
    p = v.PortfolioState(positions=[existing], cash=1_000.0)
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=10, price=100.0)
    result = v.validate_trade_proposal(proposal, p)
    check("Venta valida de una posicion existente se aprueba", result.approved)

    # --- sin operaciones intradia: buy despues de sell mismo ticker mismo dia ---
    p = v.PortfolioState(positions=[], cash=100_000.0, todays_trades=[{"ticker": "AAPL", "action": "sell"}])
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0)
    result = v.validate_trade_proposal(proposal, p)
    check("Comprar despues de vender el mismo ticker el mismo dia se rechaza", not result.approved)

    # --- sin operaciones intradia: sell despues de buy mismo ticker mismo dia ---
    existing = v.Position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=100.0)
    p = v.PortfolioState(positions=[existing], cash=1_000.0, todays_trades=[{"ticker": "AAPL", "action": "buy"}])
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=10, price=100.0)
    result = v.validate_trade_proposal(proposal, p)
    check("Vender despues de comprar el mismo ticker el mismo dia se rechaza", not result.approved)

    # --- dos compras del mismo ticker el mismo dia SI se permiten (no es round-trip) ---
    p = v.PortfolioState(positions=[], cash=100_000.0, todays_trades=[{"ticker": "AAPL", "action": "buy"}])
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0)
    result = v.validate_trade_proposal(proposal, p)
    check("Dos compras del mismo ticker el mismo dia no cuentan como round-trip", result.approved)

    # --- no se abre una posicion #13 ---
    positions = [
        v.Position(ticker=f"T{i}", quantity=1, avg_cost=100.0, current_price=100.0)
        for i in range(v.TARGET_MAX_POSITIONS)
    ]
    p = v.PortfolioState(positions=positions, cash=100_000.0)
    proposal = v.TradeProposal(ticker="NEWTICKER", action="buy", quantity=1, price=100.0)
    result = v.validate_trade_proposal(proposal, p)
    check(f"No se abre una posicion #{v.TARGET_MAX_POSITIONS + 1} nueva", not result.approved)

    # --- pero SI se puede agregar a una posicion existente aunque ya haya 12 ---
    proposal = v.TradeProposal(ticker="T0", action="buy", quantity=1, price=100.0)
    result = v.validate_trade_proposal(proposal, p)
    check("Agregar a una posicion YA existente no cuenta contra el limite de conteo", result.approved)

    # --- posicion flaggeada para revision no puede recibir mas compras ---
    existing = v.Position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=80.0)  # -20%
    p = v.PortfolioState(positions=[existing], cash=100_000.0, flagged_for_review={"AAPL"})
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=1, price=80.0)
    result = v.validate_trade_proposal(proposal, p)
    check("No se puede agregar a una posicion marcada para revision de tesis", not result.approved)

    # --- pero SI se puede vender una posicion flaggeada (salir esta permitido) ---
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=10, price=80.0)
    result = v.validate_trade_proposal(proposal, p)
    check("Se puede vender una posicion marcada para revision (salir siempre esta permitido)", result.approved)

    # --- clase de activo no permitida ---
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="BTC", action="buy", quantity=1, price=100.0, asset_class="crypto")
    result = v.validate_trade_proposal(proposal, p)
    check("Clases de activo fuera de 'stock' se rechazan", not result.approved)

    # --- warning (no bloqueo) cuando el conteo queda debajo del minimo ---
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0)
    result = v.validate_trade_proposal(proposal, p)
    check("Cartera con pocas posiciones se aprueba igual (con warning, no bloqueo)", result.approved)
    check("El warning de conteo minimo aparece", len(result.warnings) == 1)

    # --- check_thesis_review_triggers ---
    positions = [
        v.Position(ticker="DOWN20", quantity=10, avg_cost=100.0, current_price=80.0),   # exactamente -20%
        v.Position(ticker="DOWN30", quantity=10, avg_cost=100.0, current_price=70.0),   # -30%
        v.Position(ticker="FLAT", quantity=10, avg_cost=100.0, current_price=100.0),    # 0%
        v.Position(ticker="UP10", quantity=10, avg_cost=100.0, current_price=110.0),    # +10%
    ]
    p = v.PortfolioState(positions=positions, cash=0.0)
    triggered = v.check_thesis_review_triggers(p)
    check("Trigger de revision detecta exactamente las posiciones en -20% o peor",
          set(triggered) == {"DOWN20", "DOWN30"})

    # --- kill-switch de drawdown desactivado en paper trading ---
    result = v.check_drawdown_kill_switch(-0.50)  # incluso un drawdown enorme
    check("Kill-switch de drawdown esta desactivado en fase paper (siempre aprueba)", result.approved)

    print("\nTodos los tests de logica pura del validator pasaron.")


if __name__ == "__main__":
    try:
        run()
    except AssertionError as e:
        print(f"\nFALLO: {e}")
        sys.exit(1)
