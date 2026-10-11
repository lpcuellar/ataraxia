"""
Lectura del portafolio real de LP desde el CSV que exporta Schwab.

El CSV es la fuente de verdad del portafolio — reemplaza a la DB del fondo simulado.
LP sube uno nuevo cuando cambia algo; el mas reciente manda.

Formato esperado (export "Individual Positions" de Schwab):

    "Positions for account Individual ...576 as of 11:31 AM ET, 2026/09/24"
    (linea en blanco)
    "Symbol","Description","Qty (Quantity)","Price",...,"Cost Basis","Gain $ ...",...
    "AMZN","AMAZON.COM INC","5.157","246.1694",...,"$1,121.37","$148.13",...
    ...
    "Cash & Cash Investments","--","--",...
    "Positions Total","",...

Las dos ultimas filas son agregados, no posiciones.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PORTFOLIO_GLOB = "portfolio-*.csv"

# Filas que Schwab agrega al final y no son posiciones
_AGGREGATE_ROWS = {"Cash & Cash Investments", "Positions Total", "Account Total"}

# Cuantos dias puede tener el snapshot antes de considerarse viejo. El prompt
# instruye a Ataraxia a decirlo explicitamente en el reporte cuando pasa de aqui.
STALE_AFTER_DAYS = 14


@dataclass
class Position:
    ticker: str
    description: str
    quantity: float
    price: float
    market_value: float
    cost_basis: float
    gain_usd: float
    gain_pct: float
    pct_of_account: float
    asset_type: str

    @property
    def avg_cost(self) -> float:
        return self.cost_basis / self.quantity if self.quantity else 0.0

    @property
    def is_etf(self) -> bool:
        """
        Schwab reporta 'ETFs & Closed End Funds' para fondos y 'Equity' para acciones.

        Importa para los guardrails: el tope de 15% al costo existe para acotar riesgo
        idiosincratico de una empresa. Un ETF de indice ya es una canasta diversificada,
        asi que el limite no aplica — y la concentracion Carlson de 8-15 nombres se cuenta
        sobre equities, no sobre fondos.
        """
        t = self.asset_type.lower()
        return "etf" in t or "fund" in t


@dataclass
class PortfolioSnapshot:
    as_of: date
    source_file: Path
    positions: list[Position] = field(default_factory=list)
    cash: float = 0.0
    total_market_value: float = 0.0
    total_cost_basis: float = 0.0

    @property
    def total_gain_usd(self) -> float:
        return self.total_market_value - self.total_cost_basis

    @property
    def total_gain_pct(self) -> float:
        if not self.total_cost_basis:
            return 0.0
        return self.total_gain_usd / self.total_cost_basis

    @property
    def age_days(self) -> int:
        return (date.today() - self.as_of).days

    @property
    def is_stale(self) -> bool:
        return self.age_days > STALE_AFTER_DAYS

    @property
    def equities(self) -> list[Position]:
        """Acciones individuales. Los guardrails de concentracion se cuentan aqui."""
        return [p for p in self.positions if not p.is_etf]

    @property
    def etfs(self) -> list[Position]:
        return [p for p in self.positions if p.is_etf]

    def weight_at_cost(self, ticker: str) -> float:
        """Peso de una posicion sobre el costo total — la base del limite de 15%."""
        if not self.total_cost_basis:
            return 0.0
        for p in self.positions:
            if p.ticker == ticker:
                return p.cost_basis / self.total_cost_basis
        return 0.0


def to_validator_state(snapshot: "PortfolioSnapshot"):
    """
    Adapta el snapshot del CSV al PortfolioState que espera src.guardrails.validator.

    Asi los guardrails corren contra el portafolio real de LP y no contra el fondo
    simulado — que es el punto del rediseño. Mantiene el principio "el LLM propone,
    el codigo decide": el validador sigue siendo la autoridad sobre el tope de 15%.

    Solo pasa las acciones: el tope de 15% al costo y el objetivo de 8-15 nombres
    existen para acotar riesgo idiosincratico de una empresa, y un ETF de indice ya
    es una canasta diversificada.
    """
    from src.guardrails.validator import Position as VPosition
    from src.guardrails.validator import PortfolioState

    return PortfolioState(
        positions=[
            VPosition(
                ticker=p.ticker,
                quantity=p.quantity,
                avg_cost=p.avg_cost,
                current_price=p.price,
            )
            for p in snapshot.equities
        ],
        cash=snapshot.cash,
        etf_cost_basis=sum(p.cost_basis for p in snapshot.etfs),
        etf_market_value=sum(p.market_value for p in snapshot.etfs),
        todays_trades=[],  # el CSV es un snapshot, no trae operaciones del dia
        flagged_for_review={p.ticker for p in snapshot.equities if p.gain_pct <= -20},
    )


def _to_float(raw: str | None) -> float:
    """'$1,121.37' -> 1121.37 | '-1.24%' -> -1.24 | '--' o '' -> 0.0"""
    if raw is None:
        return 0.0
    cleaned = raw.strip().replace("$", "").replace(",", "").replace("%", "")
    if cleaned in {"", "--", "N/A"}:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_as_of(header: str) -> date | None:
    """Extrae la fecha de 'Positions for account ... as of 11:31 AM ET, 2026/09/24'."""
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})", header)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _date_from_filename(path: Path) -> date | None:
    """portfolio-2026-09-24.csv -> date(2026, 9, 24)"""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", path.stem)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def latest_snapshot_path(data_dir: Path | None = None) -> Path | None:
    """El CSV de portafolio mas reciente por fecha en el nombre."""
    directory = data_dir or DATA_DIR
    candidates = sorted(directory.glob(PORTFOLIO_GLOB))
    if not candidates:
        return None
    dated = [(d, p) for p in candidates if (d := _date_from_filename(p))]
    if dated:
        return max(dated, key=lambda t: t[0])[1]
    return candidates[-1]


def load_snapshot(path: Path | None = None) -> PortfolioSnapshot:
    """
    Carga el snapshot del portafolio. Sin argumento, toma el CSV mas reciente de data/.

    Lanza FileNotFoundError si no hay ninguno — es mejor fallar ruidoso que analizar
    un portafolio que no existe.
    """
    csv_path = path or latest_snapshot_path()
    if csv_path is None:
        raise FileNotFoundError(
            f"No hay ningun {PORTFOLIO_GLOB} en {DATA_DIR}. "
            "LP tiene que subir un export de posiciones de Schwab."
        )
    if not csv_path.exists():
        raise FileNotFoundError(f"No existe: {csv_path}")

    raw = csv_path.read_text(encoding="utf-8-sig")
    lines = raw.splitlines()

    as_of = _parse_as_of(lines[0]) if lines else None
    if as_of is None:
        as_of = _date_from_filename(csv_path)
    if as_of is None:
        as_of = datetime.fromtimestamp(csv_path.stat().st_mtime).date()

    # La fila de encabezados es la primera que empieza con "Symbol"
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.lstrip('"').startswith("Symbol")), None
    )
    if header_idx is None:
        raise ValueError(f"{csv_path.name}: no encontre la fila de encabezados (Symbol,...)")

    reader = csv.DictReader(lines[header_idx:])
    snapshot = PortfolioSnapshot(as_of=as_of, source_file=csv_path)

    def col(row: dict, *names: str) -> str:
        """Schwab varia los encabezados entre exports; probamos varios nombres."""
        for n in names:
            for key in row:
                if key and key.strip().lower().startswith(n.lower()):
                    return row[key] or ""
        return ""

    for row in reader:
        symbol = (col(row, "Symbol") or "").strip()
        if not symbol:
            continue

        if symbol in _AGGREGATE_ROWS:
            if symbol == "Cash & Cash Investments":
                snapshot.cash = _to_float(col(row, "Mkt Val", "Market Value"))
            elif symbol == "Positions Total":
                snapshot.total_market_value = _to_float(col(row, "Mkt Val", "Market Value"))
                snapshot.total_cost_basis = _to_float(col(row, "Cost Basis"))
            continue

        snapshot.positions.append(
            Position(
                ticker=symbol,
                description=(col(row, "Description") or "").strip(),
                quantity=_to_float(col(row, "Qty", "Quantity")),
                price=_to_float(col(row, "Price")),
                market_value=_to_float(col(row, "Mkt Val", "Market Value")),
                cost_basis=_to_float(col(row, "Cost Basis")),
                gain_usd=_to_float(col(row, "Gain $")),
                gain_pct=_to_float(col(row, "Gain %")),
                pct_of_account=_to_float(col(row, "% of Acct")),
                asset_type=(col(row, "Asset Type") or "").strip(),
            )
        )

    # Si el export no traia fila de totales, los derivamos de las posiciones
    if not snapshot.total_market_value:
        snapshot.total_market_value = sum(p.market_value for p in snapshot.positions)
    if not snapshot.total_cost_basis:
        snapshot.total_cost_basis = sum(p.cost_basis for p in snapshot.positions)

    return snapshot
