"""
Cache simple basada en archivos JSON, invalidada por dia (no por TTL fino) — Ataraxia
consulta lo mismo como maximo una vez al dia, asi que no hace falta nada mas sofisticado.
Reduce llamadas repetidas a FMP dentro del mismo dia (ahorra cuota del free tier).

Fase 1.
"""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from src.config import CACHE_DIR


def _cache_key(namespace: str, params: dict) -> str:
    raw = f"{namespace}:{sorted(params.items())}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{date.today().isoformat()}_{namespace}_{digest}.json"


def cached_call(namespace: str, params: dict, fetch_fn: Callable[[], Any]) -> Any:
    """Si ya se llamo esta combinacion namespace+params hoy, devuelve lo cacheado.
    Si no, ejecuta fetch_fn(), guarda el resultado, y lo devuelve."""
    cache_file = CACHE_DIR / _cache_key(namespace, params)

    if cache_file.exists():
        return json.loads(cache_file.read_text())

    result = fetch_fn()
    cache_file.write_text(json.dumps(result))
    return result


def clear_cache() -> int:
    """Util para forzar un refresh manual. Devuelve cuantos archivos borro."""
    count = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    return count
