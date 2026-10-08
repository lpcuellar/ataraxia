"""Pruebas sinteticas: no son recomendaciones ni ejecutan operaciones."""
import sys
from pathlib import Path
from copy import deepcopy
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.guardrails.validator import *
from src.data.portfolio_csv import load_snapshot, to_validator_state

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
assert not validate_replacement(sell,TradeProposal('NEW','buy',50,10,**bc),p,'Comparacion').approved
print('PASS: reemplazo sigue respetando limite de 15%')
s=load_snapshot(); v=to_validator_state(s)
assert len(v.positions)==len(s.equities)
assert abs(v.total_cost_basis-(s.total_cost_basis+s.cash))<.01
print('PASS: ETFs excluidos de conteo, incluidos en denominador de cartera real')
for n in (float('nan'),float('inf')):
    assert not validate_trade_proposal(TradeProposal('NEW','buy',n,10,**bc),p).approved
print('PASS: cantidades no finitas rechazadas')
