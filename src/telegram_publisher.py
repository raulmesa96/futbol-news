"""Publicación en el canal de Telegram vía Bot API.

El bot debe ser administrador del canal para poder publicar.

Sobre los reintentos: si Telegram *rechaza* la petición, el mensaje no llegó a
publicarse y reintentar es seguro. Si en cambio se pierde la conexión o expira
el tiempo de espera, no sabemos qué pasó al otro lado — el post pudo publicarse
igualmente, y reintentar ahí es justo lo que deja la noticia duplicada en el
canal. `Envio` separa los dos casos para que quien llama pueda decidir.
"""
import json
import logging
from dataclasses import dataclass

import requests

import config
from src.feeds import HEADERS

log = logging.getLogger(__name__)

API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


@dataclass
class Envio:
    """Resultado de un intento de publicación."""

    message_id: int | None = None
    # True cuando se perdió la respuesta: el mensaje pudo publicarse o no.
    incierto: bool = False

    @property
    def publicado(self) -> bool:
        return self.message_id is not None

    @property
    def reintentable(self) -> bool:
        """Solo se reintenta cuando consta que el mensaje NO se publicó."""
        return not self.publicado and not self.incierto


def _keyboard(url: str) -> dict:
    """Botón 'Ver más' bajo el post, apuntando a la noticia original."""
    return {"inline_keyboard": [[{"text": config.READ_MORE_LABEL, "url": url}]]}


def _call(method: str, **kwargs) -> Envio:
    try:
        r = requests.post(f"{API}/{method}", timeout=60, **kwargs)
    except requests.RequestException as exc:
        log.error("Telegram %s: respuesta perdida (%s)", method, exc)
        return Envio(incierto=True)

    if r.ok:
        message_id = r.json().get("result", {}).get("message_id")
        if message_id is None:
            # Respondió que sí pero sin identificador: no podemos afirmar nada.
            log.warning("Telegram %s: respuesta sin message_id: %s", method, r.text[:200])
            return Envio(incierto=True)
        return Envio(message_id=message_id)

    # 4xx = Telegram rechazó la petición y el mensaje no existe. 5xx = el fallo
    # es suyo y pudo haberlo publicado antes de reventar, así que no arriesgamos.
    log.warning("Telegram %s [%s]: %s", method, r.status_code, r.text[:300])
    return Envio(incierto=r.status_code >= 500)


def send_text(text: str, link: str) -> Envio:
    return _call(
        "sendMessage",
        json={
            "chat_id": config.TELEGRAM_CHANNEL,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": _keyboard(link),
            "link_preview_options": {"is_disabled": True},
        },
    )


def send_photo(image_url: str, caption: str, link: str) -> Envio:
    """Publica la imagen del RSS con pie de foto y botón.

    Primero se le pasa la URL a Telegram, que es lo barato. Si el medio bloquea
    a los servidores de Telegram (hotlinking, CDN quisquilloso), la descargamos
    nosotros y la subimos como fichero — pero solo si consta que el primer
    intento no publicó nada.
    """
    payload = {
        "chat_id": config.TELEGRAM_CHANNEL,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": _keyboard(link),
    }

    envio = _call("sendPhoto", json={**payload, "photo": image_url})
    if not envio.reintentable:
        return envio

    log.info("Telegram no pudo traer la imagen; la subimos nosotros: %s", image_url)
    try:
        r = requests.get(image_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("No se pudo descargar la imagen %s: %s", image_url, exc)
        return envio
    # La Bot API rechaza fotos de más de 10 MB.
    if len(r.content) > 10 * 1024 * 1024:
        log.warning("Imagen demasiado grande (%d bytes): %s", len(r.content), image_url)
        return envio

    # En multipart todo va como texto: el teclado tiene que ir serializado.
    form = {
        k: json.dumps(v) if isinstance(v, dict) else str(v)
        for k, v in payload.items()
    }
    return _call("sendPhoto", data=form, files={"photo": ("image.jpg", r.content)})


def publish(text: str, link: str, image_url: str | None) -> Envio:
    """Publica la noticia con imagen si la hay; si no, como texto."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHANNEL:
        log.error("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHANNEL en el entorno")
        return Envio()

    if image_url:
        envio = send_photo(image_url, text, link)
        if not envio.reintentable:
            return envio
        log.info("Publicando sin imagen como respaldo")
    return send_text(text, link)


def check() -> str | None:
    """Comprueba token y permisos. Devuelve el nombre del canal o None."""
    if not config.TELEGRAM_BOT_TOKEN:
        log.error("Falta TELEGRAM_BOT_TOKEN")
        return None
    try:
        me = requests.get(f"{API}/getMe", timeout=15).json()
        if not me.get("ok"):
            log.error("Token inválido: %s", me.get("description"))
            return None
        chat = requests.get(
            f"{API}/getChat",
            params={"chat_id": config.TELEGRAM_CHANNEL},
            timeout=15,
        ).json()
        if not chat.get("ok"):
            log.error("No se puede acceder al canal: %s", chat.get("description"))
            return None
        return chat["result"].get("title") or config.TELEGRAM_CHANNEL
    except requests.RequestException as exc:
        log.error("No hay conexión con Telegram: %s", exc)
        return None
