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


# Bear case/probabilidad validos por default, para no repetirlos en cada test que no esta
# probando ese guardrail especificamente.
BC = dict(bear_case="riesgo de competencia si el margen se comprime", bear_case_probability=0.2)


def run():
    # --- caso base: compra valida en cartera vacia ---
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0, **BC)  # $1,000 / 15% de 100k = $15k max
    result = v.validate_trade_proposal(proposal, p)
    check("Compra valida dentro de todos los limites se aprueba", result.approved)

    # --- limite de concentracion: 25% del costo de las ACCIONES (decision de LP 2026-10-14) ---
    # El denominador son solo las acciones: ni ETFs ni cash. Y el tope exige al menos 4
    # posiciones para ser aritmeticamente posible, asi que los casos de abajo parten de una
    # cartera ya diversificada — con menos posiciones el tope no aplica (ver su propio test).
    def sleeve(n: int, each_cost: float = 10_000.0, cash: float = 100_000.0, **kw):
        """Cartera de n acciones de igual costo, cada una en 1/n del costo de acciones."""
        positions = [
            v.Position(ticker=f"EQ{i}", quantity=100, avg_cost=each_cost / 100, current_price=each_cost / 100)
            for i in range(n)
        ]
        return v.PortfolioState(positions=positions, cash=cash, **kw)

    # 4 acciones de $10k = $40k de costo en acciones. Comprar $20k de una nueva la deja en
    # 20k/60k = 33% > 25%.
    p = sleeve(4)
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=200, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Compra que excede 25% del costo de las acciones se rechaza", not result.approved)
    check("La razon del rechazo menciona el limite", "25%" in result.reason or "maximo permitido" in result.reason)
    check("La razon aclara que ETFs y cash no cuentan", "ETFs" in result.reason)

    # Misma cartera, compra chica: $5k de una nueva -> 5k/45k = 11%. Debe aprobarse.
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=50, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Compra que queda debajo del 25% se aprueba", result.approved)

    # --- el denominador crece con la compra ---
    # 4 x $10k = $40k. Comprar $13k de una nueva: contra el denominador PREVIO seria
    # 13/40 = 32.5% (rechazo), pero el correcto es 13/53 = 24.5% (aprobacion), porque la
    # compra convierte cash en costo de accion y sube el denominador tambien.
    p = sleeve(4)
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=130, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check(
        "El denominador incluye la compra misma: 13k/53k = 24.5% se aprueba "
        "(contra el denominador previo habria dado 32.5% y bloqueado de mas)",
        result.approved,
    )

    # --- los ETFs NO entran en el denominador ---
    # Misma manga de acciones ($40k) pero con $500k de ETFs al lado. Si los ETFs contaran,
    # el porcentaje se diluiria a ~4% y la compra pasaria. Con el denominador correcto sigue
    # siendo 33% y debe rechazarse: tener un indice al lado no habilita concentrar mas.
    p = sleeve(4, etf_cost_basis=500_000.0, etf_market_value=500_000.0)
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=200, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check(
        "Los ETFs no diluyen el limite: $500k de ETFs al lado no habilitan una compra "
        "que deja 33% del costo de las acciones en un nombre",
        not result.approved,
    )

    # --- agregar a una posicion existente tambien respeta el tope ---
    # 4 x $10k; agregar $5k a una existente la deja en 15k/45k = 33% > 25%.
    p = sleeve(4)
    proposal = v.TradeProposal(ticker="EQ0", action="buy", quantity=50, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Agregar a una posicion existente tambien respeta el tope", not result.approved)

    # --- el tope es AL COSTO, no a valor de mercado ---
    # Ganadora: costo $10k (uno de 5 iguales = 20%) pero su valor de mercado se duplico. Si
    # el chequeo usara valor de mercado se rechazaria sin que se haya agregado nada; al costo,
    # agregar $1k la deja en 11k/51k = 21.6% y debe aprobarse.
    p = sleeve(5)
    p.positions[0] = v.Position(ticker="NVDA", quantity=100, avg_cost=100.0, current_price=200.0)
    proposal = v.TradeProposal(ticker="NVDA", action="buy", quantity=5, price=200.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Ganadora apreciada: el limite se mide contra el costo, no el valor de mercado inflado", result.approved)

    # Perdedora: costo $30k de $60k en acciones (50%, ya excede) pero su valor de mercado cayo
    # a $15k, que contra el mercado luciria chico. Debe rechazarse igual — este es exactamente
    # el escenario que la regla existe para evitar: promediar a la baja mas alla del costo.
    p = sleeve(3)
    p.positions.append(v.Position(ticker="PTON", quantity=300, avg_cost=100.0, current_price=50.0))
    proposal = v.TradeProposal(ticker="PTON", action="buy", quantity=1, price=50.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check(
        "Perdedora que ya excede el tope AL COSTO se rechaza aunque su valor de mercado "
        "luzca pequeño (evita promediar a la baja mas alla del limite)",
        not result.approved,
    )

    # --- el tope no se aplica cuando es aritmeticamente imposible ---
    # Con 25% hacen falta >= 4 posiciones. Con 3 o menos, cualquier compra queda arriba del
    # tope por aritmetica pura; si bloqueara, no habria forma de reconstruir una cartera y el
    # guardrail entraria en deadlock. Debe aprobar, pero avisando.
    p = sleeve(2)
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=100, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Con 3 posiciones resultantes el tope no bloquea (seria imposible de cumplir)", result.approved)
    check(
        "Pero avisa que el tope no se pudo aplicar",
        any("tope no se aplica" in w for w in result.warnings),
    )

    # Primera compra en cartera vacia: 100% del costo de acciones por construccion. No puede
    # bloquear, porque entonces nunca se podria empezar a invertir.
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=100, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("La primera compra en una cartera vacia no queda bloqueada por el tope", result.approved)

    # --- cash insuficiente ---
    p = empty_portfolio(cash=500.0)
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0, **BC)  # $1,000 > $500
    result = v.validate_trade_proposal(proposal, p)
    check("Compra sin cash suficiente se rechaza", not result.approved)

    # --- no se puede vender lo que no se tiene ---
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=10, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Vender sin posicion abierta se rechaza", not result.approved)

    # --- no se puede vender mas de lo que se tiene ---
    existing = v.Position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=100.0)
    p = v.PortfolioState(positions=[existing], cash=1_000.0)
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=20, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Vender mas cantidad de la que se tiene se rechaza", not result.approved)

    # --- venta valida ---
    existing = v.Position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=100.0)
    p = v.PortfolioState(positions=[existing], cash=1_000.0)
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=10, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Venta valida de una posicion existente se aprueba", result.approved)

    # --- sin operaciones intradia: buy despues de sell mismo ticker mismo dia ---
    p = v.PortfolioState(positions=[], cash=100_000.0, todays_trades=[{"ticker": "AAPL", "action": "sell"}])
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Comprar despues de vender el mismo ticker el mismo dia se rechaza", not result.approved)

    # --- sin operaciones intradia: sell despues de buy mismo ticker mismo dia ---
    existing = v.Position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=100.0)
    p = v.PortfolioState(positions=[existing], cash=1_000.0, todays_trades=[{"ticker": "AAPL", "action": "buy"}])
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=10, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Vender despues de comprar el mismo ticker el mismo dia se rechaza", not result.approved)

    # --- dos compras del mismo ticker el mismo dia SI se permiten (no es round-trip) ---
    p = v.PortfolioState(positions=[], cash=100_000.0, todays_trades=[{"ticker": "AAPL", "action": "buy"}])
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Dos compras del mismo ticker el mismo dia no cuentan como round-trip", result.approved)

    # --- no se abre una posicion #13 ---
    positions = [
        v.Position(ticker=f"T{i}", quantity=1, avg_cost=100.0, current_price=100.0)
        for i in range(v.TARGET_MAX_POSITIONS)
    ]
    p = v.PortfolioState(positions=positions, cash=100_000.0)
    proposal = v.TradeProposal(ticker="NEWTICKER", action="buy", quantity=1, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check(f"No se abre una posicion #{v.TARGET_MAX_POSITIONS + 1} nueva", not result.approved)

    # --- pero SI se puede agregar a una posicion existente aunque ya haya 12 ---
    proposal = v.TradeProposal(ticker="T0", action="buy", quantity=1, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Agregar a una posicion YA existente no cuenta contra el limite de conteo", result.approved)

    # --- posicion flaggeada para revision no puede recibir mas compras ---
    existing = v.Position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=80.0)  # -20%
    p = v.PortfolioState(positions=[existing], cash=100_000.0, flagged_for_review={"AAPL"})
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=1, price=80.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("No se puede agregar a una posicion marcada para revision de tesis", not result.approved)

    # --- pero SI se puede vender una posicion flaggeada (salir esta permitido) ---
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=10, price=80.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Se puede vender una posicion marcada para revision (salir siempre esta permitido)", result.approved)

    # --- el trigger de -20% se autocalcula en vivo, SIN depender de flagged_for_review ---
    existing = v.Position(ticker="TSLA", quantity=10, avg_cost=100.0, current_price=79.0)  # -21%, nada la flagueo
    p = v.PortfolioState(positions=[existing], cash=100_000.0)  # flagged_for_review vacio
    proposal = v.TradeProposal(ticker="TSLA", action="buy", quantity=1, price=79.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check(
        "El trigger de -20% bloquea la compra en vivo aunque nadie haya escrito un flag en la DB",
        not result.approved,
    )

    # --- y se autorresuelve si el precio se recupera por encima del umbral ---
    recovered = v.Position(ticker="TSLA", quantity=10, avg_cost=100.0, current_price=85.0)  # -15%, ya no dispara
    p = v.PortfolioState(positions=[recovered], cash=100_000.0)
    proposal = v.TradeProposal(ticker="TSLA", action="buy", quantity=1, price=85.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("El trigger de -20% se autorresuelve si el precio se recupera por encima del umbral", result.approved)

    # --- clase de activo no permitida ---
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="BTC", action="buy", quantity=1, price=100.0, asset_class="crypto", **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Clases de activo fuera de 'stock' se rechazan", not result.approved)

    # --- warning (no bloqueo) cuando el conteo queda debajo del minimo ---
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0, **BC)
    result = v.validate_trade_proposal(proposal, p)
    check("Cartera con pocas posiciones se aprueba igual (con warning, no bloqueo)", result.approved)
    # Se verifica el contenido, no la cantidad: una cartera chica dispara tambien el aviso de
    # que el tope de concentracion no se pudo aplicar, y contar warnings haria fallar el test
    # por un aviso extra que es correcto.
    check(
        "El warning de conteo minimo aparece",
        any("debajo del objetivo minimo" in w for w in result.warnings),
    )

    # --- bear case obligatorio ---
    p = empty_portfolio()
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0, bear_case="", bear_case_probability=0.2)
    result = v.validate_trade_proposal(proposal, p)
    check("Una propuesta sin bear case se rechaza", not result.approved)

    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0, bear_case="   ", bear_case_probability=0.2)
    result = v.validate_trade_proposal(proposal, p)
    check("Un bear case de solo espacios en blanco tambien se rechaza", not result.approved)

    # --- probabilidad del bear case debe estar en [0, 1] ---
    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0,
                                bear_case="riesgo real", bear_case_probability=1.5)
    result = v.validate_trade_proposal(proposal, p)
    check("Una probabilidad de bear case fuera de [0, 1] se rechaza", not result.approved)

    proposal = v.TradeProposal(ticker="AAPL", action="buy", quantity=10, price=100.0,
                                bear_case="riesgo real", bear_case_probability=-0.1)
    result = v.validate_trade_proposal(proposal, p)
    check("Una probabilidad de bear case negativa se rechaza", not result.approved)

    # --- exige bear case tambien en ventas (PROJECT_PLAN.md: toda compra/venta) ---
    existing = v.Position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=100.0)
    p = v.PortfolioState(positions=[existing], cash=1_000.0)
    proposal = v.TradeProposal(ticker="AAPL", action="sell", quantity=10, price=100.0,
                                bear_case="", bear_case_probability=0.2)
    result = v.validate_trade_proposal(proposal, p)
    check("Una venta sin bear case tambien se rechaza", not result.approved)

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

    # --- kill-switch de drawdown ACTIVO en -30% (decision de LP 2026-10-11) ---
    check("Kill-switch esta configurado, no en None", v.DRAWDOWN_KILL_SWITCH_PCT == -0.30)
    check("Drawdown del 50% dispara el kill-switch",
          not v.check_drawdown_kill_switch(-0.50).approved)
    check("Drawdown exactamente en el umbral (-30%) dispara",
          not v.check_drawdown_kill_switch(-0.30).approved)
    check("Drawdown del 25% NO dispara (ruido esperado en cartera concentrada)",
          v.check_drawdown_kill_switch(-0.25).approved)
    check("Sin drawdown, aprueba", v.check_drawdown_kill_switch(0.0).approved)

    print("\nTodos los tests de logica pura del validator pasaron.")


if __name__ == "__main__":
    try:
        run()
    except AssertionError as e:
        print(f"\nFALLO: {e}")
        sys.exit(1)
