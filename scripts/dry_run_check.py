#!/usr/bin/env python3
"""
Arnes de dry-run: corre el ciclo con escrituras bloqueadas y verifica que no cambio nada.

Por que hace falta un arnes y no basta con --dry-run: los flags viven dentro del codigo
que se esta probando. Si run_cycle olvida propagar el flag a un subproceso, o si un script
escribe por un camino que nadie recordaba, el flag no lo detiene. Este arnes pone la
barrera afuera:

  1. Transaccion de solo lectura a nivel de conexion (set_session(readonly=True)), con
     verificacion explicita de SHOW transaction_read_only antes de seguir. La opcion
     default_transaction_read_only en la cadena de conexion no alcanza — hay que pedirla
     en la sesion y confirmarla.

  2. Bloqueo del fallback a disco. src/db/models._write_with_fallback atrapa el error de
     una escritura rechazada y la encola en data/pending_db_writes/ para reintentarla
     despues. Sin bloquear eso, una escritura "impedida" reaparece en el proximo ciclo
     real. El modo de solo lectura de Postgres no protege colas de archivos.

  3. Huellas antes y despues: conteo de filas y hash del contenido ordenado de cada tabla,
     mas el inventario de pending_db_writes/. Una diferencia pide investigacion — puede
     ser un escritor concurrente, no necesariamente este dry-run.

Lo que este arnes NO prueba: que Ataraxia produzca un buen reporte. Los scripts arman el
contexto; el analisis lo hace el agente leyendo src/agent/prompt.py. Preparar la mesa no
es haber comido.

Uso:
    python scripts/dry_run_check.py barrido
    python scripts/dry_run_check.py reporte
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.config import PENDING_WRITES_DIR, require_db_config  # noqa: E402

PY = str(REPO / "venv" / "bin" / "python")
TABLES = [
    "watchlist",
    "candidate_queue",
    "recommendations",
    "portfolio_snapshots",
    "universe_state",
    "decisions",
]
SUBPROCESS_TIMEOUT = 300


def _readonly_conn():
    """
    Conexion con transaccion de solo lectura, verificada.

    set_session(readonly=True) se pide explicitamente porque pasar
    default_transaction_read_only por options no basta para establecerla.
    """
    import psycopg2

    conn = psycopg2.connect(**require_db_config())
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("SHOW transaction_read_only")
        got = cur.fetchone()[0]
    if got != "on":
        conn.close()
        raise RuntimeError(
            f"La conexion NO quedo en solo lectura (transaction_read_only={got!r}). "
            "Abortado: sin esa garantia el dry-run puede escribir."
        )
    return conn


def fingerprint() -> dict:
    """Conteo y hash del contenido de cada tabla, mas la cola de escrituras en disco."""
    conn = _readonly_conn()
    out: dict = {"tablas": {}}
    try:
        with conn.cursor() as cur:
            for t in TABLES:
                try:
                    cur.execute(f"select * from {t} order by 1")
                    rows = cur.fetchall()
                except Exception as e:
                    conn.rollback()
                    out["tablas"][t] = {"error": type(e).__name__}
                    continue
                blob = "\n".join(repr(r) for r in rows).encode()
                out["tablas"][t] = {
                    "filas": len(rows),
                    "hash": hashlib.sha256(blob).hexdigest()[:16],
                }
    finally:
        conn.close()

    pend = sorted(p.name for p in PENDING_WRITES_DIR.glob("*.json")) \
        if PENDING_WRITES_DIR.exists() else []
    out["pending_db_writes"] = {"archivos": len(pend), "nombres": pend}
    return out


def diff(before: dict, after: dict) -> list[str]:
    problems = []
    for t in TABLES:
        b, a = before["tablas"].get(t, {}), after["tablas"].get(t, {})
        if b.get("filas") != a.get("filas"):
            problems.append(f"{t}: filas {b.get('filas')} -> {a.get('filas')}")
        elif b.get("hash") != a.get("hash"):
            problems.append(f"{t}: mismo conteo pero el contenido cambio")

    pb, pa = before["pending_db_writes"], after["pending_db_writes"]
    if pb["nombres"] != pa["nombres"]:
        nuevos = set(pa["nombres"]) - set(pb["nombres"])
        idos = set(pb["nombres"]) - set(pa["nombres"])
        if nuevos:
            problems.append(f"pending_db_writes: {len(nuevos)} archivo(s) nuevo(s) — "
                            "una escritura bloqueada se encolo para reintentar")
        if idos:
            problems.append(f"pending_db_writes: {len(idos)} archivo(s) menos — se hizo flush")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flujo", choices=["barrido", "reporte"])
    args = ap.parse_args()

    print("=" * 70)
    print(f"DRY-RUN: {args.flujo}")
    print("=" * 70)

    print("\n1. Verificando transaccion de solo lectura...")
    before = fingerprint()
    print("   OK — SHOW transaction_read_only = on")

    print("\n2. Estado antes:")
    for t, v in before["tablas"].items():
        if "error" in v:
            print(f"   {t:22} (sin acceso: {v['error']})")
        else:
            print(f"   {t:22} {v['filas']:>4} filas  {v['hash']}")
    print(f"   {'pending_db_writes':22} {before['pending_db_writes']['archivos']:>4} archivos")

    print(f"\n3. Corriendo run_cycle.py {args.flujo} --dry-run")
    print("   (escrituras bloqueadas: conexion de solo lectura + fallback a disco inhabilitado)")
    print("-" * 70)

    env = {
        **os.environ,
        # Lo lee src/db/models para rechazar escrituras antes de que el fallback
        # las mande a pending_db_writes/
        "ATARAXIA_DRY_RUN": "1",
        "PGOPTIONS": "-c default_transaction_read_only=on",
    }
    try:
        r = subprocess.run(
            [PY, str(REPO / "scripts" / "run_cycle.py"), args.flujo, "--dry-run"],
            env=env, timeout=SUBPROCESS_TIMEOUT,
        )
        rc = r.returncode
    except subprocess.TimeoutExpired:
        print(f"\n!! El flujo excedio {SUBPROCESS_TIMEOUT}s y fue cortado.")
        rc = 124

    print("-" * 70)
    print(f"   codigo de salida: {rc}")

    print("\n4. Estado despues:")
    after = fingerprint()
    problems = diff(before, after)
    for t, v in after["tablas"].items():
        if "error" in v:
            continue
        b = before["tablas"][t]
        mark = "  <-- CAMBIO" if (b.get("filas") != v["filas"] or b.get("hash") != v["hash"]) else ""
        print(f"   {t:22} {v['filas']:>4} filas  {v['hash']}{mark}")
    print(f"   {'pending_db_writes':22} {after['pending_db_writes']['archivos']:>4} archivos")

    print("\n" + "=" * 70)
    if problems:
        print("ESTADO MODIFICADO — el dry-run no fue limpio:")
        for p in problems:
            print(f"  - {p}")
        print("\nRevisar si fue este flujo o un escritor concurrente antes de concluir.")
    else:
        print("ESTADO PRESERVADO — ninguna tabla ni la cola de disco cambiaron.")

    print("\nQue se ejercito:")
    print("  - lectura del portafolio real desde el CSV de Schwab")
    print("  - lectura de watchlist, cola y bitacora contra Supabase")
    print("  - guardrails de concentracion y sustitucion")
    print("Que NO se ejercito:")
    print("  - encolado de candidatos ni avance de la rotacion del universo")
    print("  - flush de escrituras pendientes")
    print("  - el analisis de Ataraxia: estos scripts arman el contexto, no lo reemplazan")
    print("=" * 70)

    return 1 if (problems or rc != 0) else 0


if __name__ == "__main__":
    sys.exit(main())
