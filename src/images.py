"""Adaptación de las imágenes de los medios a lo que Instagram acepta.

Telegram traga cualquier cosa; Instagram no. Exige JPEG (Mundo Deportivo sirve
WEBP, y encima con extensión .jpeg, así que no basta con mirar la URL), un
ancho mínimo y una proporción dentro de un rango estrecho. Aquí se arregla todo
eso antes de subir nada.
"""
import io
import logging
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.feeds import HEADERS

log = logging.getLogger(__name__)

# Fuentes a probar, en orden. La primera es la que se instala en el corredor de
# GitHub Actions (fonts-dejavu-core); las dos siguientes son de Windows, para
# que las pruebas en local se vean igual.
FUENTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _fuente(tamano: int) -> ImageFont.FreeTypeFont:
    for ruta in FUENTES:
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tamano)
    log.warning("Sin fuente TrueType: el titular saldrá en la fuente por defecto")
    return ImageFont.load_default()

# Requisitos de la API de publicación de Instagram.
RATIO_MIN = 0.80          # 4:5, vertical máximo
RATIO_MAX = 1.91          # 1.91:1, horizontal máximo
ANCHO_MINIMO = 320
ANCHO_MAXIMO = 1440       # más ancho no aporta: Instagram reescala
CALIDAD = 88

# Las stories son 9:16. Una foto apaisada se pega centrada sobre un fondo
# tomado de la propia imagen, que queda mejor que barras negras.
RATIO_STORY = 9 / 16


def descargar(url: str) -> Image.Image | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content))
    except (requests.RequestException, OSError) as exc:
        log.warning("No se pudo abrir la imagen %s: %s", url, exc)
        return None


def _recortar_al_rango(img: Image.Image) -> Image.Image:
    """Recorta centrado hasta que la proporción entre en el rango de Instagram.

    Se recorta en vez de añadir márgenes porque una foto de prensa aguanta bien
    perder los bordes, y las barras se ven como un error.
    """
    w, h = img.size
    ratio = w / h
    if ratio > RATIO_MAX:                      # demasiado apaisada: estrechar
        nuevo_ancho = int(h * RATIO_MAX)
        izq = (w - nuevo_ancho) // 2
        return img.crop((izq, 0, izq + nuevo_ancho, h))
    if ratio < RATIO_MIN:                      # demasiado alta: acortar
        nueva_altura = int(w / RATIO_MIN)
        arriba = (h - nueva_altura) // 2
        return img.crop((0, arriba, w, arriba + nueva_altura))
    return img


def para_publicacion(url: str) -> bytes | None:
    """Imagen lista para el feed: JPEG, proporción y tamaño válidos."""
    img = descargar(url)
    if img is None:
        return None

    img = _recortar_al_rango(img.convert("RGB"))
    if img.width > ANCHO_MAXIMO:
        alto = int(img.height * ANCHO_MAXIMO / img.width)
        img = img.resize((ANCHO_MAXIMO, alto), Image.LANCZOS)
    if img.width < ANCHO_MINIMO:
        log.warning("Imagen demasiado pequeña (%dpx): %s", img.width, url)
        return None

    salida = io.BytesIO()
    img.save(salida, format="JPEG", quality=CALIDAD, optimize=True)
    return salida.getvalue()


def _escribir_titular(lienzo: Image.Image, titular: str, fuente_pie: str) -> None:
    """Dibuja el titular sobre la franja inferior de la story.

    Las stories no admiten pie de texto: o el titular va encima de la imagen o
    la noticia se publica sin contar nada.
    """
    ancho, alto = lienzo.size
    margen = int(ancho * 0.075)
    tam = int(ancho * 0.058)
    fuente = _fuente(tam)
    fuente_via = _fuente(int(tam * 0.62))

    # ~26 caracteres por línea a este tamaño; se limita a 4 líneas.
    lineas = textwrap.wrap(titular, width=26)[:4]
    alto_linea = int(tam * 1.28)
    alto_texto = alto_linea * len(lineas) + int(tam * 1.6)

    # Degradado oscuro de abajo arriba: la foto sigue viéndose y el texto se
    # lee sobre cualquier fondo, que es el problema de escribir sobre fotos.
    inicio = alto - alto_texto - margen * 2
    degradado = Image.new("L", (1, alto - inicio))
    for y in range(degradado.height):
        degradado.putpixel((0, y), int(235 * (y / degradado.height) ** 0.65))
    sombra = Image.new("RGB", (ancho, alto - inicio), (0, 0, 0))
    lienzo.paste(sombra, (0, inicio), degradado.resize((ancho, alto - inicio)))

    dibujo = ImageDraw.Draw(lienzo)
    y = alto - margen - alto_texto + int(tam * 0.4)
    for linea in lineas:
        dibujo.text((margen, y), linea, font=fuente, fill=(255, 255, 255))
        y += alto_linea
    dibujo.text((margen, y + int(tam * 0.15)), fuente_pie, font=fuente_via,
                fill=(200, 200, 200))


def para_story(url: str, titular: str = "", via: str = "") -> bytes | None:
    """Imagen lista para una story: lienzo 9:16 con la foto y el titular.

    El fondo es la propia foto ampliada y desenfocada, que es lo que hacen las
    apps de edición: rellena el vertical sin que parezca un error de formato.
    """
    img = descargar(url)
    if img is None:
        return None
    img = img.convert("RGB")

    alto = 1920
    ancho = int(alto * RATIO_STORY)            # 1080x1920

    # Fondo: la foto recortada a 9:16 y desenfocada.
    escala = max(ancho / img.width, alto / img.height)
    fondo = img.resize((int(img.width * escala) + 1, int(img.height * escala) + 1),
                       Image.LANCZOS)
    izq = (fondo.width - ancho) // 2
    arriba = (fondo.height - alto) // 2
    fondo = fondo.crop((izq, arriba, izq + ancho, arriba + alto))
    fondo = fondo.filter(ImageFilter.GaussianBlur(28))

    # Primer plano: la foto entera, centrada, ocupando el ancho disponible.
    escala = min(ancho / img.width, alto / img.height)
    frente = img.resize((int(img.width * escala), int(img.height * escala)),
                        Image.LANCZOS)
    # La foto se sube un poco: abajo va el titular y no debe taparla.
    fondo.paste(frente, ((ancho - frente.width) // 2,
                         int((alto - frente.height) * 0.38)))

    if titular:
        _escribir_titular(fondo, titular, via)

    salida = io.BytesIO()
    fondo.save(salida, format="JPEG", quality=CALIDAD, optimize=True)
    return salida.getvalue()
