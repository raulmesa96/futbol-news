"""Construcción del texto del post a partir de la noticia del RSS."""
import re
from html import escape

import config
from src import dedup
from src.feeds import Article

# Límites duros de la Bot API. Nos dejamos margen para no pelearnos con el
# recuento exacto de caracteres de Telegram.
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096
MARGIN = 40


def truncate(text: str, limit: int) -> str:
    """Recorta por la última palabra entera que quepa."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-–—")
    return f"{cut}…"


def _useful_summary(article: Article) -> str:
    """Resumen del feed, salvo que sea el titular repetido o esté vacío."""
    summary = article.summary.strip()
    if not summary:
        return ""
    if dedup.similarity(dedup.title_key(article.title), dedup.title_key(summary)) >= 0.9:
        return ""
    return summary


def _patron(palabras) -> re.Pattern:
    """Regex que casa cualquiera de las palabras, enteras.

    Los límites de palabra son lo que impide que "precio" pique en "precioso"
    o "gol" en "golpe".
    """
    return re.compile("|".join(r"\b%s\b" % re.escape(p) for p in palabras))


_SIN_EMOJI = _patron(config.EMOJI_NONE)
_REGLAS = [(_patron(palabras), emoji) for palabras, emoji in config.EMOJI_RULES]

# Cita entre comillas dobles con contenido suficiente para ser una frase y no
# un apodo. Se aplica sobre el titular original, no sobre el normalizado.
_CITA = re.compile(r'[«"“][^»"”]{15,}[»"”]')


def emoji_for(title: str) -> str:
    """Emoji que encabeza el post, según lo que cuenta el titular.

    Devuelve cadena vacía en noticias de luto o sucesos: estos feeds mezclan
    fichajes con muertes y accidentes, y un 🔥 encima de un obituario es
    exactamente el tipo de cosa que hunde un canal.
    """
    texto = dedup.strip_accents(title.lower())
    if _SIN_EMOJI.search(texto):
        return ""
    for patron, emoji in _REGLAS:
        if patron.search(texto):
            return emoji
    if config.EMOJI_QUOTE and _CITA.search(title):
        return config.EMOJI_QUOTE
    return config.EMOJI_DEFAULT


def build(article: Article, *, with_image: bool) -> str:
    """Texto HTML del post.

    `with_image` cambia el presupuesto de caracteres: los pies de foto de
    Telegram admiten 1024 y los mensajes de texto 4096.
    """
    limit = (CAPTION_LIMIT if with_image else TEXT_LIMIT) - MARGIN

    title = escape(truncate(article.title, 200))
    source = escape(article.source)
    footer = f"📰 {source}"

    emoji = emoji_for(article.title)
    parts = [f"{emoji} <b>{title}</b>" if emoji else f"<b>{title}</b>"]
    summary = _useful_summary(article)
    if summary:
        # Lo que quede libre tras titular y pie, con tope propio de config.
        budget = min(config.SUMMARY_MAX_CHARS, limit - len(title) - len(footer) - 8)
        if budget > 60:
            parts.append(escape(truncate(summary, budget)))
    parts.append(footer)

    return "\n\n".join(parts)
