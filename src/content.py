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
    cut = text[:limit]
    corte = max(cut.rfind(" "), cut.rfind("\n"))
    if corte > 0:
        cut = cut[:corte]
    return f"{cut.rstrip(' \n,.;:-–—')}…"


# Un párrafo más corto que esto y sin puntuación final no es una frase: es un
# ladillo del artículo. Sin marcarlo, en el post queda como una línea suelta.
SUBTITULO_MAX = 80


def formatear(texto: str) -> str:
    """Escapa el resumen y marca en negrita los ladillos del artículo."""
    parrafos = []
    for i, parrafo in enumerate(texto.split("\n\n")):
        p = escape(parrafo.strip())
        if not p:
            continue
        if i and len(p) <= SUBTITULO_MAX and not p.endswith((".", "!", "?", "…", '"', "»", ":")):
            p = f"<b>{p}</b>"
        parrafos.append(p)
    return "\n\n".join(parrafos)


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
_BANDERAS = [(_patron(clubes), bandera) for bandera, clubes in config.CLUB_FLAGS]

# Cita entre comillas dobles con contenido suficiente para ser una frase y no
# un apodo. Se aplica sobre el titular original, no sobre el normalizado.
_CITA = re.compile(r'[«"“][^»"”]{15,}[»"”]')


def flags_for(text: str) -> str:
    """Banderas de los países implicados, solo si la noticia cruza fronteras.

    Con un solo país no se devuelve nada: un 🇪🇸 delante de cada noticia de
    LaLiga saldría en la mitad de los posts y no diría nada que el lector no
    supiera. Con dos o más, en cambio, resume la historia de un vistazo.
    """
    normalizado = dedup.strip_accents(text.lower())
    encontradas = [b for patron, b in _BANDERAS if patron.search(normalizado)]
    return "".join(encontradas[:3]) if len(encontradas) >= 2 else ""


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
    footer = f"{config.VIA_LABEL} {source}"

    # Las banderas mandan sobre el emoji de tema: si la noticia cruza fronteras,
    # eso es lo primero que interesa saber.
    cabecera = flags_for(f"{article.title} {article.summary}") or emoji_for(article.title)
    parts = [f"{cabecera} <b>{title}</b>" if cabecera else f"<b>{title}</b>"]

    summary = _useful_summary(article)
    if summary:
        # Lo que quede libre tras titular y pie, con tope propio de config.
        budget = min(config.SUMMARY_MAX_CHARS, limit - len(title) - len(footer) - 8)
        if budget > 60:
            parts.append(formatear(truncate(summary, budget)))
    parts.append(footer)

    return "\n\n".join(parts)
