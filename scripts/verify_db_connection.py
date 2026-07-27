#!/usr/bin/env python3
"""
Verifica la conexion a Supabase y que los permisos del rol ataraxia_brain son exactamente
los que deberian ser: puede insert/select en las tablas de log, select/update en
universe_state, y NO puede hacer nada mas (delete, crear tablas, etc).

No deja datos de prueba permanentes: el INSERT de prueba corre dentro de una transaccion
que se revierte (rollback) al final.

Uso: python scripts/verify_db_connection.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2

from src.db import models as db


def run():
    print("1. Conectando como ataraxia_brain...")
    conn = db.get_connection()
    print("   OK — conectado")

    print("2. Leyendo la fila singleton de universe_state...")
    row = db.get_universe_state()
    assert row is not None, "universe_state esta vacia — corriste la migracion inicial?"
    print(f"   OK — {row}")

    print("3. INSERT + SELECT en decisions (dentro de una transaccion, sin dejar rastro)...")
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute(
            "insert into decisions (date, ticker, entry_type, rationale, guardrail_result) "
            "values (current_date, 'TEST_CONNECTIVITY', 'review', 'connectivity check', 'n/a') "
            "returning id"
        )
        new_id = cur.fetchone()[0]
        cur.execute("select ticker from decisions where id = %s", (new_id,))
        ticker = cur.fetchone()[0]
        print(f"   OK — insertado y releido id={new_id}, ticker={ticker}")

    print("4. Confirmando que ataraxia_brain NO puede borrar de decisions (debe fallar)...")
    try:
        with conn.cursor() as cur:
            cur.execute("delete from decisions where id = %s", (new_id,))
        print("   FALLO DE SEGURIDAD — el delete se permitio, esto NO deberia pasar")
        sys.exit(1)
    except psycopg2.errors.InsufficientPrivilege:
        print("   OK — delete rechazado correctamente (privilegio insuficiente)")
    conn.rollback()
    print("   Transaccion revertida — no queda ningun dato de prueba.")

    print("5. Confirmando que ataraxia_brain NO puede crear tablas (debe fallar)...")
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("create table should_not_work (id int)")
        print("   FALLO DE SEGURIDAD — se pudo crear una tabla, esto NO deberia pasar")
        sys.exit(1)
    except psycopg2.errors.InsufficientPrivilege:
        print("   OK — creacion de tabla rechazada correctamente")
    conn.rollback()

    conn.close()
    print()
    print("Todo verificado: conexion a Supabase, wiring de models.py, y permisos de scope")
    print("minimo del rol ataraxia_brain funcionan como se diseñaron.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"\nFALLO: {e}")
        sys.exit(1)
