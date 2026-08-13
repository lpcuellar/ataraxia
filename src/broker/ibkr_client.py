"""
Cliente del IBKR Client Portal (Web) API, hablando con el Gateway que IBeam mantiene
autenticado (ver docker/docker-compose.yml).

Decisiones ya tomadas (PROJECT_PLAN.md Seccion 3):
  - Client Portal API, NO TWS API (TWS no puede correr headless)
  - Cuenta de paper trading primero, siempre, antes de cualquier capital real
  - En fase paper no hay 2FA — IBeam sostiene la sesion solo. La 2FA diaria vuelve a ser
    tema recien en la graduacion a cuenta real (Fase 6).

SOLO el executor usa este modulo. El brain no lo importa nunca — estructuralmente no tiene
como llegar a IBKR (no corre donde esta el gateway, no tiene las credenciales).

Flujo de una orden (endpoints confirmados contra la doc oficial del Web API):
  1. GET  /iserver/accounts                      — despierta el subsistema de ordenes
  2. GET  /iserver/secdef/search?symbol=X        — resolver ticker -> conid
  3. POST /iserver/account/{acct}/orders         — colocar orden MKT/DAY
  4. POST /iserver/reply/{replyId}               — confirmar los "question prompts" que el
     API devuelve (precauciones estandar de IBKR); se confirman en loop hasta recibir order_id
  5. GET  /iserver/account/orders                — poll de estado hasta Filled/timeout

Ordenes de mercado (MKT) a proposito: Ataraxia es un inversor de largo plazo cuya tesis no
depende de centavos de precision de entrada, y una MKT en horario de mercado sobre acciones
del S&P 500 llena de inmediato. El precio real del fill (no el estimado de la propuesta) es
lo que se registra en executed_trades.

El gateway usa un certificado self-signed en localhost -> verify=False es esperado aqui
(la conexion no sale de la maquina/red de contenedores).
"""

import os
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_GATEWAY_URL = "https://localhost:5000"
FILL_POLL_SECONDS = 3
FILL_TIMEOUT_SECONDS = 90
MAX_REPLY_CONFIRMATIONS = 6


class IBKRError(RuntimeError):
    pass


class IBKRClient:
    def __init__(self, gateway_url: str | None = None):
        self.base = (gateway_url or os.getenv("IBEAM_GATEWAY_URL", DEFAULT_GATEWAY_URL)).rstrip("/")
        self.api = f"{self.base}/v1/api"
        self.session = requests.Session()
        self.session.verify = False
        self._account_id: str | None = None

    def _get(self, path: str, **params) -> dict | list:
        resp = self.session.get(f"{self.api}{path}", params=params or None, timeout=30)
        if resp.status_code >= 300:
            raise IBKRError(f"GET {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def _post(self, path: str, payload: dict | None = None) -> dict | list:
        resp = self.session.post(f"{self.api}{path}", json=payload, timeout=30)
        if resp.status_code >= 300:
            raise IBKRError(f"POST {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    # ------------------------------------------------------------------
    # Sesion / cuenta
    # ------------------------------------------------------------------

    def is_authenticated(self) -> bool:
        try:
            status = self._post("/iserver/auth/status")
            return bool(status.get("authenticated"))
        except Exception:
            return False

    def keepalive(self) -> None:
        """/tickle mantiene viva la sesion. IBeam ya lo hace por su cuenta; esto es un
        extra barato al inicio de cada corrida del executor."""
        self._post("/tickle")

    def get_account_id(self) -> str:
        """Tambien 'despierta' el subsistema de ordenes — IBKR requiere llamar
        /iserver/accounts antes de operar en una sesion nueva."""
        if self._account_id:
            return self._account_id
        data = self._get("/iserver/accounts")
        accounts = data.get("accounts") if isinstance(data, dict) else data
        if not accounts:
            raise IBKRError("El gateway no devolvio cuentas — sesion no autenticada?")
        env_acct = os.getenv("IBKR_ACCOUNT_ID", "")
        if env_acct:
            if env_acct not in accounts:
                raise IBKRError(
                    f"IBKR_ACCOUNT_ID={env_acct} no esta entre las cuentas del gateway: {accounts}"
                )
            self._account_id = env_acct
        else:
            self._account_id = accounts[0]
        return self._account_id

    # ------------------------------------------------------------------
    # Contratos
    # ------------------------------------------------------------------

    def find_conid(self, ticker: str) -> int:
        """Resuelve un ticker de accion US a su conid. Prefiere el listing NASDAQ/NYSE."""
        results = self._get("/iserver/secdef/search", symbol=ticker)
        if not results:
            raise IBKRError(f"secdef/search no encontro nada para '{ticker}'")
        stocks = [
            r for r in results
            if r.get("symbol") == ticker and "STK" in str(r.get("secType", r.get("sections", "")))
        ] or [r for r in results if r.get("symbol") == ticker] or results
        conid = stocks[0].get("conid")
        if conid is None:
            raise IBKRError(f"resultado de secdef/search sin conid para '{ticker}': {stocks[0]}")
        return int(conid)

    # ------------------------------------------------------------------
    # Ordenes
    # ------------------------------------------------------------------

    def place_market_order(self, ticker: str, action: str, quantity: float) -> dict:
        """Coloca una orden MKT/DAY y espera el fill.

        SOLO se llama despues de que la propuesta paso por src/guardrails/validator.py en el
        executor — nunca directamente desde el brain.

        Devuelve {"filled": bool, "fill_price": float, "fill_quantity": float,
                  "order_id": str, "status": str}
        """
        side = action.upper()
        if side not in ("BUY", "SELL"):
            raise IBKRError(f"accion invalida: {action}")

        account_id = self.get_account_id()
        conid = self.find_conid(ticker)

        payload = {
            "orders": [
                {
                    "conid": conid,
                    "orderType": "MKT",
                    "side": side,
                    "quantity": quantity,
                    "tif": "DAY",
                }
            ]
        }
        response = self._post(f"/iserver/account/{account_id}/orders", payload)
        order_id = self._resolve_order_confirmations(response)
        return self._wait_for_fill(order_id, ticker)

    def _resolve_order_confirmations(self, response) -> str:
        """El API devuelve 'question prompts' (advertencias estandar) que hay que confirmar
        via /iserver/reply/{id} antes de que la orden quede colocada. Se confirman en loop
        acotado; si despues de MAX_REPLY_CONFIRMATIONS sigue preguntando, algo raro pasa y
        se aborta con error en vez de confirmar a ciegas para siempre."""
        for _ in range(MAX_REPLY_CONFIRMATIONS):
            if isinstance(response, list) and response and "order_id" in response[0]:
                return str(response[0]["order_id"])
            if isinstance(response, list) and response and "id" in response[0]:
                reply_id = response[0]["id"]
                response = self._post(f"/iserver/reply/{reply_id}", {"confirmed": True})
                continue
            raise IBKRError(f"respuesta inesperada al colocar orden: {response}")
        raise IBKRError("demasiados prompts de confirmacion seguidos — abortando por seguridad")

    def _find_order(self, order_id: str) -> dict | None:
        data = self._get("/iserver/account/orders")
        for order in data.get("orders", []):
            if str(order.get("orderId")) == order_id:
                return order
        return None

    def _wait_for_fill(self, order_id: str, ticker: str) -> dict:
        """Poll hasta Filled o timeout. En timeout intenta cancelar y reporta el estado
        final REAL — nunca inventa un fill, y nunca deja una orden viva sin reportarlo."""
        deadline = time.time() + FILL_TIMEOUT_SECONDS
        last_status = "unknown"
        while time.time() < deadline:
            order = self._find_order(order_id)
            if order:
                last_status = str(order.get("status", "unknown"))
                if last_status.lower() == "filled":
                    return {
                        "filled": True,
                        "fill_price": float(order.get("avgPrice") or order.get("price") or 0),
                        "fill_quantity": float(order.get("filledQuantity") or order.get("totalSize") or 0),
                        "order_id": order_id,
                        "status": last_status,
                    }
                if last_status.lower() in ("cancelled", "inactive", "rejected"):
                    return {"filled": False, "fill_price": 0.0, "fill_quantity": 0.0,
                            "order_id": order_id, "status": last_status}
            time.sleep(FILL_POLL_SECONDS)

        # Timeout: intentar cancelar, luego chequear una ultima vez (la orden pudo llenarse
        # en la ventana entre el ultimo poll y el cancel).
        try:
            account_id = self.get_account_id()
            self.session.delete(
                f"{self.api}/iserver/account/{account_id}/order/{order_id}", timeout=30
            )
        except Exception:
            pass
        time.sleep(FILL_POLL_SECONDS)
        order = self._find_order(order_id)
        if order and str(order.get("status", "")).lower() == "filled":
            return {
                "filled": True,
                "fill_price": float(order.get("avgPrice") or order.get("price") or 0),
                "fill_quantity": float(order.get("filledQuantity") or order.get("totalSize") or 0),
                "order_id": order_id,
                "status": "Filled",
            }
        final = str(order.get("status")) if order else last_status
        return {"filled": False, "fill_price": 0.0, "fill_quantity": 0.0,
                "order_id": order_id, "status": f"timeout ({final})"}

    # ------------------------------------------------------------------
    # Lectura de cuenta (para reconciliacion / smoke tests)
    # ------------------------------------------------------------------

    def get_positions(self) -> list[dict]:
        account_id = self.get_account_id()
        return self._get(f"/portfolio/{account_id}/positions/0")
