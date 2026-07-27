"""
Configuracion centralizada: carga .env y expone valores usados por el resto del pipeline.

Fase 1.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

FMP_API_KEY = os.getenv("FMP_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ATARAXIA_ENV = os.getenv("ATARAXIA_ENV", "development")

# --- Supabase (Postgres) — conexion directa con el rol acotado ataraxia_brain, no el
# cliente supabase-py ni las keys anon/service_role. Ver src/db/schema.sql. ---
SUPABASE_DB_HOST = os.getenv("SUPABASE_DB_HOST", "")
SUPABASE_DB_PORT = os.getenv("SUPABASE_DB_PORT", "5432")
SUPABASE_DB_NAME = os.getenv("SUPABASE_DB_NAME", "postgres")
SUPABASE_DB_USER = os.getenv("SUPABASE_DB_USER", "ataraxia_brain")
SUPABASE_DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD", "")

DATA_DIR = ROOT_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_DIR = ROOT_DIR / "config"
PENDING_WRITES_DIR = DATA_DIR / "pending_db_writes"

DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)
PENDING_WRITES_DIR.mkdir(exist_ok=True)


def require_fmp_key() -> str:
    """Lanza un error claro si falta la API key, en vez de fallar mas adelante con un 401
    confuso desde requests."""
    if not FMP_API_KEY:
        raise RuntimeError(
            "FMP_API_KEY no esta configurada. Copia .env.example a .env y llena tu API key "
            "de Financial Modeling Prep (gratis en https://site.financialmodelingprep.com/)."
        )
    return FMP_API_KEY


def require_db_config() -> dict:
    """Lanza un error claro si falta algun dato de conexion a Supabase."""
    if not SUPABASE_DB_HOST or not SUPABASE_DB_PASSWORD:
        raise RuntimeError(
            "Faltan SUPABASE_DB_HOST y/o SUPABASE_DB_PASSWORD en .env. Corre "
            "src/db/schema.sql en el SQL Editor de Supabase primero, pon una password real "
            "al rol ataraxia_brain (linea 'create role...'), y copia el host de connection "
            "string de tu proyecto (Settings > Database)."
        )
    return {
        "host": SUPABASE_DB_HOST,
        "port": SUPABASE_DB_PORT,
        "dbname": SUPABASE_DB_NAME,
        "user": SUPABASE_DB_USER,
        "password": SUPABASE_DB_PASSWORD,
    }
