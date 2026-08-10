"""Descarga de feeds RSS y normalización a un modelo común de noticia.

Cada medio publica el RSS a su manera (la imagen puede venir en media:content,
en un enclosure, incrustada en el HTML del resumen o directamente no venir), así
que aquí se aplana todo a `Article` y el resto del pipeline ya no se entera de
las diferencias entre Marca, Sport o quien sea.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import requests

import config

log = logging.getLogger(__name__)

# Los medios españoles suelen bloquear el user-agent por defecto de feedparser.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
}

# Parámetros de tracking: dos enlaces que solo difieren en esto son el mismo.
TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "s", "ref", "cmpid", "_ga"}

TAG_RE = re.compile(r"<[^>]+>")
# Varios medios cierran la descripción con un enlace "Leer más"; al quitar las
# etiquetas queda el texto del enlace colgando al final del resumen.
TRAILING_JUNK_RE = re.compile(
    r"[\s.·|–—-]*(leer(\s+m[áa]s)?|seguir\s+leyendo|ver\s+m[áa]s|continuar\s+leyendo)"
    r"[\s.·|…]*$",
    re.I,
)
IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
OG_IMAGE_REVERSED_RE = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I
)


@dataclass
class Article:
    source: str
    title: str
    summary: str
    link: str
    image: str | None
    published: datetime | None
    guid: str


def canonical_url(url: str) -> str:
    """Quita parámetros de tracking y el fragmento para poder comparar enlaces."""
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return url.strip()
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunparse((parts.scheme, parts.netloc.lower(), path, "", urlencode(query), ""))


def clean_text(raw: str) -> str:
    """HTML del resumen -> texto plano de una sola línea."""
    if not raw:
        return ""
    text = TAG_RE.sub(" ", raw)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Quitar los <a> de dentro del texto deja el espacio delante del signo de
    # puntuación que los seguía: "Oyarzabal , clave en...".
    text = re.sub(r"\s+([,.;:!?%）)\]])", r"\1", text)
    return TRAILING_JUNK_RE.sub("", text)


def _entry_image(entry) -> str | None:
    """Primera imagen utilizable de la entrada, probando todos los formatos."""
    # media:content — puede haber varias resoluciones; nos quedamos la mayor.
    media = [m for m in getattr(entry, "media_content", []) if m.get("url")]
    if media:
        def width(m):
            try:
                return int(m.get("width") or 0)
            except (TypeError, ValueError):
                return 0

        return max(media, key=width)["url"]

    for thumb in getattr(entry, "media_thumbnail", []):
        if thumb.get("url"):
            return thumb["url"]

    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("image/") and enc.get("url"):
            return enc["url"]

    for link in getattr(entry, "links", []):
        if link.get("rel") == "enclosure" and link.get("type", "").startswith("image/"):
            return link.get("href")

    # Último recurso dentro del feed: un <img> incrustado en el cuerpo.
    bodies = [c.get("value", "") for c in getattr(entry, "content", [])]
    bodies.append(getattr(entry, "summary", "") or "")
    for body in bodies:
        match = IMG_SRC_RE.search(body)
        if match:
            return unescape(match.group(1))

    return None


def scrape_og_image(url: str) -> str | None:
    """og:image de la propia noticia, para feeds que no adjuntan imagen."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.debug("No se pudo leer %s para la og:image: %s", url, exc)
        return None
    # Con los primeros 200 KB basta: og:image va en el <head>.
    html = r.text[:200_000]
    match = OG_IMAGE_RE.search(html) or OG_IMAGE_REVERSED_RE.search(html)
    return unescape(match.group(1)) if match else None


def _published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def fetch(source: str, url: str) -> list[Article]:
    """Lee un feed y devuelve sus entradas como `Article`."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Feed caído %s (%s): %s", source, url, exc)
        return []

    parsed = feedparser.parse(r.content)
    if parsed.bozo and not parsed.entries:
        log.warning("Feed ilegible %s (%s): %s", source, url, parsed.bozo_exception)
        return []

    articles = []
    for entry in parsed.entries:
        link = getattr(entry, "link", "")
        title = clean_text(getattr(entry, "title", ""))
        if not link or not title:
            continue
        link = canonical_url(link)
        articles.append(
            Article(
                source=source,
                title=title,
                summary=clean_text(getattr(entry, "summary", "")),
                link=link,
                image=_entry_image(entry),
                published=_published(entry),
                guid=getattr(entry, "id", "") or link,
            )
        )
    log.info("%s: %d entradas", source, len(articles))
    return articles


def fetch_all() -> list[Article]:
    """Todas las fuentes de config.FEEDS, de más reciente a más antigua."""
    articles: list[Article] = []
    for source, url in config.FEEDS:
        articles.extend(fetch(source, url))
    articles.sort(key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc))
    return articles
