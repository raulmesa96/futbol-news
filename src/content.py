"""Construcción del texto del post a partir de la noticia del RSS."""
import re
from html import escape

import config
from src import dedup
from src.feeds import Article

# Límites duros de la Bot API. El margen absorbe lo que añade el formato
# (emojis por párrafo, saltos de línea) sobre el texto que se presupuestó.
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096
MARGIN = 90

# Un párrafo más corto que esto y sin puntuación final no es una frase: es un
# ladillo del artículo. Sin marcarlo, en el post queda como una línea suelta.
SUBTITULO_MAX = 80

# Fin de frase: punto (o cierre de interrogación/exclamación) seguido de
# espacio y del arranque de otra frase. No es infalible —"Sr. García" la parte
# en dos— pero en titulares y entradillas deportivas se comporta bien.
FIN_FRASE = re.compile(r'(?<=[.!?…])\s+(?=[¿¡"«“(\dA-ZÁÉÍÓÚÑ])')


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
CITA = re.compile(r'[«"“][^»"”]{15,}[»"”]')


# Cuánto del texto disponible hay que conservar para que merezca la pena
# cortar en un punto y seguido en vez de a media frase.
CORTE_MINIMO = 0.6


def truncate(text: str, limit: int) -> str:
    """Recorta el texto, terminando en punto siempre que se pueda.

    Cortar a media frase deja colgando fragmentos como "Se convirtió en un…".
    Si hay un final de frase razonablemente cerca del límite, se corta ahí y el
    post acaba limpio; si no, se recorta por palabra entera con puntos
    suspensivos.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]

    finales = list(re.finditer(r'[.!?…]["»”]?(?=\s|$)', cut))
    if finales and finales[-1].end() >= limit * CORTE_MINIMO:
        return cut[:finales[-1].end()]

    corte = max(cut.rfind(" "), cut.rfind("\n"))
    if corte > 0:
        cut = cut[:corte]
    return f"{cut.rstrip(' \n,.;:-–—')}…"


def es_sensible(text: str) -> bool:
    """Luto, sucesos, juicios: la noticia va sin ningún emoji decorativo.

    Estos feeds mezclan fichajes con muertes y accidentes con toda naturalidad,
    y un 🔥 encima de un obituario es de las pocas cosas capaces de hundir un
    canal.
    """
    return bool(_SIN_EMOJI.search(dedup.strip_accents(text.lower())))


def flags_for(text: str) -> str:
    """Banderas de los países implicados, solo si la noticia cruza fronteras.

    Con un solo país no se devuelve nada: un 🇪🇸 delante de cada noticia de
    LaLiga saldría en la mitad de los posts y no diría nada que el lector no
    supiera. Con dos o más, en cambio, resume la historia de un vistazo.
    """
    normalizado = dedup.strip_accents(text.lower())
    encontradas = [b for patron, b in _BANDERAS if patron.search(normalizado)]
    return "".join(encontradas[:3]) if len(encontradas) >= 2 else ""


def emoji_for(text: str, default: str = config.EMOJI_DEFAULT) -> str:
    """Emoji que corresponde a un texto según lo que cuenta.

    `default` se devuelve cuando no encaja ninguna regla. Los párrafos lo piden
    vacío para poder caer en su propia lista de emojis neutros.
    """
    normalizado = dedup.strip_accents(text.lower())
    for patron, emoji in _REGLAS:
        if patron.search(normalizado):
            return emoji
    if config.EMOJI_QUOTE and CITA.search(text):
        return config.EMOJI_QUOTE
    return default


def _es_ladillo(parrafo: str) -> bool:
    return (len(parrafo) <= SUBTITULO_MAX
            and not parrafo.endswith((".", "!", "?", "…", '"', "»", ":")))


def partir_en_parrafos(texto: str) -> list[tuple[str, bool]]:
    """Trocea el resumen en párrafos cortos. Devuelve (texto, es_ladillo).

    Los medios que publican el artículo entero lo mandan en bloques de varias
    frases; leerlo así en el móvil es un muro. Se corta por frases hasta llegar
    a `PARAGRAPH_CHARS`, sin unir nunca dos párrafos que ya venían separados.
    """
    salida: list[tuple[str, bool]] = []
    for bloque in texto.split("\n\n"):
        bloque = bloque.strip()
        if not bloque:
            continue
        if _es_ladillo(bloque):
            salida.append((bloque, True))
            continue
        actual = ""
        for frase in FIN_FRASE.split(bloque):
            actual = f"{actual} {frase}".strip()
            if len(actual) >= config.PARAGRAPH_CHARS:
                salida.append((actual, False))
                actual = ""
        if actual:
            salida.append((actual, False))
    return salida


def formatear(texto: str, *, con_emojis: bool) -> str:
    """Escapa el resumen, lo trocea y encabeza cada párrafo con un emoji."""
    partes = []
    neutros = config.PARAGRAPH_FALLBACK
    anterior = ""
    for i, (parrafo, es_ladillo) in enumerate(partir_en_parrafos(texto)):
        p = escape(parrafo)
        if es_ladillo:
            partes.append(f"<b>{p}</b>")
            continue
        if not con_emojis:
            partes.append(p)
            continue
        # El emoji temático manda, pero no dos veces seguidas: párrafos
        # contiguos del mismo artículo hablan de lo mismo y saldría repetido.
        emoji = emoji_for(parrafo, default="")
        if not emoji or emoji == anterior:
            emoji = neutros[i % len(neutros)]
        anterior = emoji
        partes.append(f"{emoji} {p}")
    return "\n\n".join(partes)


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
    footer = f"{config.VIA_LABEL} {source}"

    sensible = es_sensible(article.title)
    if sensible:
        cabecera = ""
    else:
        # Las banderas mandan sobre el emoji de tema: si la noticia cruza
        # fronteras, eso es lo primero que interesa saber.
        cabecera = (flags_for(f"{article.title} {article.summary}")
                    or emoji_for(article.title))

    parts = [f"{cabecera} <b>{title}</b>" if cabecera else f"<b>{title}</b>"]

    summary = _useful_summary(article)
    if summary:
        # Lo que quede libre tras titular y pie, con tope propio de config.
        budget = min(config.SUMMARY_MAX_CHARS, limit - len(title) - len(footer) - 8)
        if budget > 60:
            parts.append(formatear(truncate(summary, budget),
                                   con_emojis=not sensible))
    parts.append(footer)

    return "\n\n".join(parts)
