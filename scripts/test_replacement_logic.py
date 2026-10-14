"""Pruebas sinteticas: no son recomendaciones ni ejecutan operaciones."""
import sys
from pathlib import Path
from copy import deepcopy
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.guardrails.validator import *
from src.data.portfolio_csv import load_latest, to_validator_state

bc = dict(bear_case='Riesgo hipotetico de competencia', bear_case_probability=.2)
p = PortfolioState([Position(f'T{i}', 10, 10, 10) for i in range(15)])
before = deepcopy(p)
sell = TradeProposal('T0', 'sell', 10, 10, **bc)
buy = TradeProposal('NEW', 'buy', 10, 10, **bc)
assert validate_replacement(sell, buy, p, 'Comparacion sintetica').approved
assert p == before
print('PASS: 15 posiciones -> venta completa + compra, sin mutar cartera')
assert not validate_replacement(TradeProposal('T0','sell',5,10,**bc), TradeProposal('NEW','buy',5,10,**bc), p,'Comparacion').approved
print('PASS: venta parcial no libera lugar numero 16')
assert not validate_replacement(sell,buy,p,'Comparacion',costs=1).approved
assert not validate_replacement(sell,buy,p,'').approved
print('PASS: efectivo insuficiente y ausencia de tesis bloquean reemplazo')
p.cash=1000
# 15 posiciones de $100; vender T0 deja $1,400 y comprar $500 de NEW la pone en
# 500/1900 = 26.3%, arriba del tope de 25% sobre el costo de las acciones.
assert not validate_replacement(sell,TradeProposal('NEW','buy',50,10,**bc),p,'Comparacion').approved
print(f'PASS: reemplazo sigue respetando el tope de {MAX_POSITION_PCT:.0%}')
s=load_latest(); v=to_validator_state(s)
assert len(v.positions)==len(s.equities)
# total_cost_basis sigue incluyendo ETFs y cash: lo usan el reporte y compute_performance.
assert abs(v.total_cost_basis-(s.total_cost_basis+s.cash))<.01
# Pero el denominador del tope de concentracion es solo acciones (LP 2026-10-14). En la
# cartera real los ETFs son ~31% del costo, asi que confundirlos no es un detalle.
assert abs(v.equity_cost_basis-sum(e.cost_basis for e in s.equities))<.01
assert v.equity_cost_basis < v.total_cost_basis
print('PASS: ETFs en total_cost_basis (reporte) pero fuera de equity_cost_basis (tope)')
for n in (float('nan'),float('inf')):
    assert not validate_trade_proposal(TradeProposal('NEW','buy',n,10,**bc),p).approved
print('PASS: cantidades no finitas rechazadas')
