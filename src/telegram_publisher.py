"""Publicación en el canal de Telegram vía Bot API.

El bot debe ser administrador del canal para poder publicar.
"""
import json
import logging

import requests

import config
from src.feeds import HEADERS

log = logging.getLogger(__name__)

API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def _keyboard(url: str) -> dict:
    """Botón 'Ver más' bajo el post, apuntando a la noticia original."""
    return {"inline_keyboard": [[{"text": config.READ_MORE_LABEL, "url": url}]]}


def _call(method: str, **kwargs) -> int | None:
    """Llama a la Bot API. Devuelve el message_id o None si falló."""
    try:
        r = requests.post(f"{API}/{method}", timeout=60, **kwargs)
    except requests.RequestException as exc:
        log.error("Telegram %s: error de red: %s", method, exc)
        return None
    if not r.ok:
        log.warning("Telegram %s: %s", method, r.text[:300])
        return None
    return r.json().get("result", {}).get("message_id")


def send_text(text: str, link: str) -> int | None:
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


def send_photo(image_url: str, caption: str, link: str) -> int | None:
    """Publica la imagen del RSS con pie de foto y botón.

    Primero se le pasa la URL a Telegram, que es lo barato. Si el medio bloquea
    a los servidores de Telegram (hotlinking, CDN quisquilloso), la descargamos
    nosotros y la subimos como fichero.
    """
    payload = {
        "chat_id": config.TELEGRAM_CHANNEL,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": _keyboard(link),
    }

    message_id = _call("sendPhoto", json={**payload, "photo": image_url})
    if message_id:
        return message_id

    log.info("Telegram no pudo traer la imagen; la subimos nosotros: %s", image_url)
    try:
        r = requests.get(image_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("No se pudo descargar la imagen %s: %s", image_url, exc)
        return None
    # La Bot API rechaza fotos de más de 10 MB.
    if len(r.content) > 10 * 1024 * 1024:
        log.warning("Imagen demasiado grande (%d bytes): %s", len(r.content), image_url)
        return None

    # En multipart todo va como texto: el teclado tiene que ir serializado.
    form = {
        k: json.dumps(v) if isinstance(v, dict) else str(v)
        for k, v in payload.items()
    }
    return _call(
        "sendPhoto",
        data=form,
        files={"photo": ("image.jpg", r.content)},
    )


def publish(text: str, link: str, image_url: str | None) -> int | None:
    """Publica la noticia con imagen si la hay; si no, como texto."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHANNEL:
        log.error("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHANNEL en el .env")
        return None
    if image_url:
        message_id = send_photo(image_url, text, link)
        if message_id:
            return message_id
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
