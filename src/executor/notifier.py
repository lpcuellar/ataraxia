"""
Notificador de mensajeria — abstraccion delgada para que el canal (WhatsApp hoy, otro
mañana) sea intercambiable sin tocar el resto del executor.

WhatsApp via Meta Cloud API (decision del usuario). Realidades de esa API que este modulo
absorbe:
  - Mensajes iniciados por el negocio FUERA de una ventana de servicio de 24h requieren un
    template pre-aprobado. Ataraxia empuja updates diarios por iniciativa propia, asi que
    el camino por defecto es un template de utilidad con una variable de cuerpo.
  - El cuerpo de un template soporta max ~1024 caracteres -> los resumenes largos se parten
    en chunks y se mandan como mensajes consecutivos.
  - Setup (una vez, en developers.facebook.com): app de Meta -> WhatsApp -> numero de prueba
    (permite hasta 5 destinatarios verificados sin verificacion de negocio) -> token
    permanente de system user -> registrar un template (p.ej. "ataraxia_update" con {{1}}
    en el cuerpo, categoria UTILITY).

Config (.env):
  WHATSAPP_ACCESS_TOKEN     token permanente de system user
  WHATSAPP_PHONE_NUMBER_ID  id del numero emisor (el de prueba o uno propio)
  WHATSAPP_RECIPIENT        numero destino en formato E.164 sin '+' (p.ej. 502XXXXXXXX)
  WHATSAPP_TEMPLATE_NAME    nombre del template aprobado (default: ataraxia_update)
  WHATSAPP_TEMPLATE_LANG    codigo de idioma del template (default: es)
"""

import os

import requests

GRAPH_API_VERSION = "v23.0"
TEMPLATE_BODY_LIMIT = 1024


def _config() -> dict:
    cfg = {
        "token": os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
        "phone_number_id": os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
        "recipient": os.getenv("WHATSAPP_RECIPIENT", ""),
        "template_name": os.getenv("WHATSAPP_TEMPLATE_NAME", "ataraxia_update"),
        "template_lang": os.getenv("WHATSAPP_TEMPLATE_LANG", "es"),
    }
    missing = [k for k in ("token", "phone_number_id", "recipient") if not cfg[k]]
    if missing:
        raise RuntimeError(
            f"Config de WhatsApp incompleta en .env: faltan {missing}. "
            "Ver el docstring de src/executor/notifier.py para el setup."
        )
    return cfg


def _chunks(text: str, limit: int = TEMPLATE_BODY_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > limit:
            parts.append(current)
            current = ""
        current += line
    if current:
        parts.append(current)
    return parts


def send_update(text: str) -> None:
    """Manda un update por WhatsApp usando el template aprobado. Los textos largos se parten
    en varios mensajes. Lanza excepcion si la API responde error — el caller decide si eso
    es fatal (no deberia serlo: una notificacion fallida no debe frenar la ejecucion)."""
    cfg = _config()
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{cfg['phone_number_id']}/messages"
    headers = {"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"}

    for chunk in _chunks(text):
        payload = {
            "messaging_product": "whatsapp",
            "to": cfg["recipient"],
            "type": "template",
            "template": {
                "name": cfg["template_name"],
                "language": {"code": cfg["template_lang"]},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": chunk}]}
                ],
            },
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code >= 300:
            raise RuntimeError(f"WhatsApp API error {resp.status_code}: {resp.text}")


def notify_safe(text: str) -> bool:
    """Version que nunca lanza: una notificacion fallida se loguea y se sigue. La ejecucion
    de trades jamas debe depender de que WhatsApp este disponible."""
    try:
        send_update(text)
        return True
    except Exception as e:
        print(f"AVISO: fallo la notificacion de WhatsApp ({e}). La ejecucion continua.")
        return False
