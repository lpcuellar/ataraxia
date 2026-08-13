#!/usr/bin/env python3
"""
Smoke test del Gateway de IBKR — SOLO lecturas, no coloca ninguna orden.

Verifica: sesion autenticada, cuenta visible, resolucion ticker->conid, y lectura de
posiciones. Correr con el contenedor de IBeam ya arriba:

    docker compose -f docker/docker-compose.yml --env-file .env up -d ibeam
    # esperar ~1-2 min a que autentique, luego:
    python scripts/smoke_test_ibkr.py

(Desde fuera de Docker el gateway esta en https://localhost:5000; desde el contenedor del
executor, en https://ibeam:5000 — IBEAM_GATEWAY_URL controla cual se usa.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.broker.ibkr_client import IBKRClient


def run():
    client = IBKRClient()
    print(f"Gateway: {client.base}")

    print("1. Verificando autenticacion...")
    if not client.is_authenticated():
        print("   FALLO — el gateway no esta autenticado. Revisar: docker compose logs ibeam")
        sys.exit(1)
    print("   OK — sesion autenticada")

    print("2. Leyendo cuenta...")
    account_id = client.get_account_id()
    is_paper = account_id.startswith("DU")  # cuentas paper de IBKR empiezan con DU
    print(f"   OK — cuenta {account_id} ({'PAPER' if is_paper else 'REAL ⚠️'})")
    if not is_paper:
        print("   ADVERTENCIA: esta NO parece una cuenta paper. Ataraxia no debe correr")
        print("   contra una cuenta real en esta fase. Abortando.")
        sys.exit(1)

    print("3. Resolviendo AAPL -> conid...")
    conid = client.find_conid("AAPL")
    print(f"   OK — conid {conid}")

    print("4. Leyendo posiciones actuales...")
    positions = client.get_positions()
    print(f"   OK — {len(positions)} posicion(es) en la cuenta")

    print("\nGateway funcional de punta a punta (sin ordenes colocadas).")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"\nFALLO: {e}")
        sys.exit(1)
