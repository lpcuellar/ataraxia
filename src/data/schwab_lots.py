"""
Lectura del export "Lot Details" de Schwab — un archivo por ticker, con una fila por lote.

Por que existe este modulo aparte de portfolio_csv.py:
  - portfolio_csv.py lee el export "Positions": un solo archivo con todas las posiciones ya
    agregadas, sin fechas de compra. Comodo de bajar, pero pierde el detalle de lotes.
  - Este modulo lee los "Lot Details": un archivo por ticker, con la fecha de apertura, el
    costo y el holding period de CADA compra. Mas trabajo de bajar, pero es la unica forma de
    saber cuando se compro cada cosa.

El detalle de lotes no se puede reconstruir despues a partir del agregado, asi que cuando
estan disponibles los Lot Details, mandan.

Formato de cada archivo (verificado contra el export del 2026-10-08):

    "VOO Lot Details for  ...576 as of 07:59 PM ET, 10/08/2026","","",...
    (linea en blanco)
    "Open Date","Quantity","Price","Cost/Share","Market Value","Cost Basis",...
    "09/30/2026","0.0076","$711.85","$703.947368","$5.41","$5.35",...
    ...
    "Total","4.2043","--","$530.685251","$2992.83","$2231.16",...

El ticker viene en la primera linea, no en las filas. La ultima fila es un agregado.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

# ETFs conocidos en la cuenta de LP. La clasificacion importa: LP decidio (2026-10-11) que el
# alpha de Ataraxia se mide solo sobre equities, porque los ETFs amplios son ancla pasiva
# fuera del mandato del agente — y VOO literalmente *es* el benchmark.
#
# Lista explicita en vez de heuristica a proposito: adivinar por nombre o por longitud de
# ticker falla silenciosamente, y una clasificacion equivocada contamina la medicion del
# proposito del proyecto. Si aparece un ticker nuevo que no esta aqui, classify_asset()
# avisa en vez de asumir.
KNOWN_ETFS = {
    "VOO", "VTI", "VXUS", "VEA", "VWO", "VT", "VUG", "VTV", "VIG", "VYM",
    "SCHD", "SCHG", "SCHB", "SCHX", "SCHA", "SCHF", "SCHE",
    "ITOT", "IVV", "IJH", "IJR", "IEFA", "IEMG", "AGG", "TLT",
    "SPY", "QQQ", "DIA", "IWM", "IWV", "RSP",
}

_HEADER_RE = re.compile(
    r'^"?(?P<ticker>[A-Z.\-]{1,6})\s+Lot Details.*as of\s+'
    r'(?P<time>\d{1,2}:\d{2}\s*[AP]M)\s+ET,\s*(?P<date>\d{2}/\d{2}/\d{4})',
    re.IGNORECASE,
)

_AGGREGATE_FIRST_CELL = {"Total", "Totals", ""}


class SchwabLotParseError(ValueError):
    """El archivo no tiene el formato esperado. Se lanza en vez de devolver datos parciales:
    un portafolio incompleto cargado en silencio es peor que un error ruidoso."""


@dataclass
class Lot:
    ticker: str
    asset_class: str
    open_date: date
    quantity: float
    cost_per_share: float
    cost_basis: float
    price_at_snapshot: float | None
    market_value: float | None
    holding_period: str | None


@dataclass
class LotSnapshot:
    as_of: date
    lots: list[Lot] = field(default_factory=list)
    cash: float = 0.0
    source_files: list[str] = field(default_factory=list)
    unknown_asset_classes: list[str] = field(default_factory=list)

    @property
    def total_cost_basis(self) -> float:
        return sum(l.cost_basis for l in self.lots)

    @property
    def total_market_value(self) -> float:
        return sum(l.market_value or 0.0 for l in self.lots)

    @property
    def tickers(self) -> set[str]:
        return {l.ticker for l in self.lots}

    def count_by_class(self, asset_class: str) -> int:
        return len({l.ticker for l in self.lots if l.asset_class == asset_class})

    def equities_only(self) -> list[Lot]:
        """Los lotes que entran en la medicion de alpha (ver KNOWN_ETFS)."""
        return [l for l in self.lots if l.asset_class == "equity"]


def _stock_symbols() -> set[str]:
    """Simbolos del screener de acciones de Nasdaq. Los ETFs no aparecen ahi, asi que
    pertenecer a esta lista es evidencia positiva de que el ticker es una accion y no un
    fondo. Se consulta con cache (ver src/data/cache.py), no en cada lote.

    us_only=False a proposito: aca la pregunta es "¿esto es una accion?", no "¿es elegible
    para el universo de candidatos?". LP tiene posiciones de empresas no estadounidenses
    listadas en EE.UU. (p.ej. BN, canadiense) que son acciones igual."""
    from src.data import fundamentals
    try:
        return {row["symbol"] for row in fundamentals.get_us_stocks_with_market_cap(us_only=False)}
    except Exception:
        # Sin red o con la fuente caida, se degrada a la lista estatica de ETFs en vez de
        # fallar: clasificar es util pero no debe impedir leer el portafolio.
        return set()


def classify_asset(ticker: str, stock_symbols: set[str] | None = None) -> tuple[str, bool]:
    """Devuelve (asset_class, es_conocido).

    es_conocido=False significa que se asumio 'equity' sin evidencia — el caller debe
    reportarlo, no silenciarlo: un ETF mal clasificado como equity entraria en la medicion
    de alpha, que es exactamente lo que LP decidio excluir.
    """
    if ticker in KNOWN_ETFS:
        return "etf", True
    if stock_symbols and ticker in stock_symbols:
        return "equity", True
    return "equity", False


def _money(raw: str) -> float | None:
    """'$1,234.56' -> 1234.56 ; '--' / '' -> None. Los negativos de Schwab vienen como
    '-$4.68', no como '($4.68)'."""
    if raw is None:
        return None
    s = raw.strip().replace("$", "").replace(",", "")
    if s in {"", "--", "N/A"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_lot_details_file(path: Path) -> tuple[str, date, list[Lot]]:
    """Parsea un archivo de Lot Details. Devuelve (ticker, fecha_del_corte, lotes)."""
    return _parse_lot_details_file(path, stock_symbols=None)


def _parse_lot_details_file(
    path: Path,
    stock_symbols: set[str] | None,
) -> tuple[str, date, list[Lot]]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines:
        raise SchwabLotParseError(f"{path.name}: archivo vacio")

    header = _HEADER_RE.match(lines[0])
    if not header:
        raise SchwabLotParseError(
            f"{path.name}: la primera linea no parece un encabezado de Lot Details de "
            f"Schwab. Esperado algo como '\"VOO Lot Details for ...576 as of 07:59 PM ET, "
            f"10/08/2026\"'. Recibido: {lines[0][:120]!r}"
        )

    ticker = header.group("ticker").upper()
    as_of = datetime.strptime(header.group("date"), "%m/%d/%Y").date()
    asset_class, _known = classify_asset(ticker, stock_symbols)

    # La fila de columnas es la que empieza con "Open Date"; las filas de datos vienen
    # despues. Se busca en vez de asumir que es la linea 3, porque Schwab mete una linea en
    # blanco cuyo formato ya cambio antes.
    reader = list(csv.reader(lines))
    col_row = next(
        (i for i, row in enumerate(reader) if row and row[0].strip() == "Open Date"),
        None,
    )
    if col_row is None:
        raise SchwabLotParseError(
            f"{path.name}: no se encontro la fila de columnas que empieza con 'Open Date'."
        )

    lots: list[Lot] = []
    for row in reader[col_row + 1:]:
        if not row or not row[0].strip():
            continue
        first = row[0].strip()
        if first in _AGGREGATE_FIRST_CELL:
            continue  # fila "Total", no un lote

        try:
            open_date = datetime.strptime(first, "%m/%d/%Y").date()
        except ValueError:
            # Ni fecha ni agregado conocido: formato inesperado, no se adivina.
            raise SchwabLotParseError(
                f"{path.name}: fila con primera celda {first!r}, que no es una fecha "
                f"MM/DD/YYYY ni una fila de total reconocida."
            )

        quantity = _money(row[1]) if len(row) > 1 else None
        if quantity is None or quantity <= 0:
            raise SchwabLotParseError(
                f"{path.name}: lote del {first} sin cantidad valida ({row[1]!r})."
            )

        cost_per_share = _money(row[3]) if len(row) > 3 else None
        cost_basis = _money(row[5]) if len(row) > 5 else None
        if cost_basis is None and cost_per_share is not None:
            cost_basis = cost_per_share * quantity
        if cost_per_share is None and cost_basis is not None:
            cost_per_share = cost_basis / quantity
        if cost_basis is None or cost_per_share is None:
            raise SchwabLotParseError(
                f"{path.name}: lote del {first} sin costo (ni Cost/Share ni Cost Basis)."
            )

        holding = row[8].strip() if len(row) > 8 and row[8].strip() in {"Short Term", "Long Term"} else None

        lots.append(Lot(
            ticker=ticker,
            asset_class=asset_class,
            open_date=open_date,
            quantity=quantity,
            cost_per_share=cost_per_share,
            cost_basis=cost_basis,
            price_at_snapshot=_money(row[2]) if len(row) > 2 else None,
            market_value=_money(row[4]) if len(row) > 4 else None,
            holding_period=holding,
        ))

    if not lots:
        raise SchwabLotParseError(f"{path.name}: encabezado valido pero cero lotes.")

    return ticker, as_of, lots


def parse_lot_details_dir(
    directory: Path,
    pattern: str = "*.csv",
    cash: float = 0.0,
) -> LotSnapshot:
    """Parsea todos los Lot Details de un directorio en un solo snapshot.

    Exige que todos los archivos sean del mismo corte: mezclar fechas produciria un
    portafolio que nunca existio en ningun momento. Si hay mas de una fecha, falla.
    """
    files = sorted(p for p in directory.glob(pattern) if p.is_file())
    if not files:
        raise SchwabLotParseError(f"No se encontro ningun CSV en {directory} ({pattern}).")

    all_lots: list[Lot] = []
    dates: dict[date, list[str]] = {}
    unknown: list[str] = []
    used: list[str] = []

    # Se resuelve una sola vez para todo el directorio, no por archivo.
    stock_symbols = _stock_symbols()

    for path in files:
        ticker, as_of, lots = _parse_lot_details_file(path, stock_symbols)
        _, known = classify_asset(ticker, stock_symbols)
        if not known:
            unknown.append(ticker)
        dates.setdefault(as_of, []).append(path.name)
        all_lots.extend(lots)
        used.append(path.name)

    if len(dates) > 1 :
        detail = "; ".join(
            f"{d.isoformat()}: {', '.join(names)}" for d, names in sorted(dates.items())
        )
        raise SchwabLotParseError(
            "Los archivos no son del mismo corte, asi que juntarlos daria un portafolio "
            f"que nunca existio. Fechas encontradas -> {detail}"
        )

    as_of = next(iter(dates))
    return LotSnapshot(
        as_of=as_of,
        lots=all_lots,
        cash=cash,
        source_files=used,
        unknown_asset_classes=sorted(set(unknown)),
    )
