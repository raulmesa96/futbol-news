"""Construcción del texto del post a partir de la noticia del RSS."""
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


def build(article: Article, *, with_image: bool) -> str:
    """Texto HTML del post.

    `with_image` cambia el presupuesto de caracteres: los pies de foto de
    Telegram admiten 1024 y los mensajes de texto 4096.
    """
    limit = (CAPTION_LIMIT if with_image else TEXT_LIMIT) - MARGIN

    title = escape(truncate(article.title, 200))
    source = escape(article.source)
    footer = f"📰 {source}"

    parts = [f"<b>{title}</b>"]
    summary = _useful_summary(article)
    if summary:
        # Lo que quede libre tras titular y pie, con tope propio de config.
        budget = min(config.SUMMARY_MAX_CHARS, limit - len(title) - len(footer) - 8)
        if budget > 60:
            parts.append(escape(truncate(summary, budget)))
    parts.append(footer)

    return "\n\n".join(parts)
