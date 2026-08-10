"""Configuración central del agregador de noticias."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "news.db"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "")

# --- Fuentes ------------------------------------------------------------------
# (nombre visible, URL del feed). El nombre sale en el pie del post, así que
# escríbelo como quieras que se lea en el canal.
# Para añadir una fuente basta con meterla aquí: el resto del pipeline es
# genérico y no sabe nada de medios concretos.
# Todos estos están comprobados y traen imagen en el 100% de las entradas.
# Ojo al añadir: usa siempre feeds de la sección de fútbol. Los feeds
# generalistas de un diario deportivo meten NBA, tenis y motor en el canal.
FEEDS = [
    ("Marca", "https://e00-marca.uecdn.es/rss/futbol/primera-division.xml"),
    ("Marca", "https://e00-marca.uecdn.es/rss/futbol/champions-league.xml"),
    ("Marca", "https://e00-marca.uecdn.es/rss/futbol/mas-futbol.xml"),
    ("Mundo Deportivo", "https://www.mundodeportivo.com/feed/rss/futbol"),
    ("Sport", "https://www.sport.es/es/rss/futbol/rss.xml"),
    ("AS", "https://as.com/rss/futbol/primera.xml"),
    ("AS", "https://as.com/rss/futbol/internacional.xml"),
    # Otros comprobados que puedes activar:
    # ("Marca", "https://e00-marca.uecdn.es/rss/futbol/premier-league.xml"),
    # ("AS", "https://as.com/rss/futbol/portada.xml"),
]

# --- Filtros ------------------------------------------------------------------

# No publicar noticias con más de estas horas: un feed puede traer piezas
# viejas la primera vez que lo lees, y el canal quedaría raro.
MAX_AGE_HOURS = 12

# Tope de publicaciones por ejecución. Si el script corre cada 30 min, 3 por
# ejecución ya son ~144 al día: sube esto solo si de verdad quieres ese ritmo.
MAX_POSTS_PER_RUN = 1

# Segundos de pausa entre publicaciones. Telegram limita ~20 mensajes/minuto
# por canal; con 3s vas holgado y los posts no llegan todos de golpe.
SECONDS_BETWEEN_POSTS = 3

# Palabras que descartan una noticia (minúsculas, sin acentos). Útil para
# quitar directos, quinielas o secciones que no quieres en el canal.
BLOCKLIST = ["horoscopo", "quiniela", "en directo | minuto a minuto"]

# Si la noticia no trae ninguna imagen en el RSS, ¿la publicamos igual como
# mensaje de texto? False = se descarta.
POST_WITHOUT_IMAGE = True

# Cuando el RSS no trae imagen, entrar en la noticia a buscar la og:image.
# Cuesta una petición HTTP extra por noticia sin imagen.
SCRAPE_OG_IMAGE = True

# --- Deduplicación ------------------------------------------------------------

# Días que se guarda una noticia en la base para compararla con las nuevas.
# Más días = menos repeticiones, base más grande (irrelevante a esta escala).
DEDUP_WINDOW_DAYS = 7

# Parecido mínimo entre dos titulares para considerarlos la misma noticia
# (0-1, ver src/dedup.py). Esto es lo que evita publicar el mismo fichaje
# contado por Marca, Sport y MD. Calibrado contra 426 titulares reales de los
# feeds: a 0.56 detecta las 12 repeticiones que había sin un solo falso
# positivo, y el peor caso conocido (dos titulares cortos que solo comparten
# "abre la puerta") se queda en 0.50, con margen. Bájalo si se cuelan
# repetidas; súbelo si te come noticias distintas del mismo equipo.
TITLE_SIMILARITY = 0.56

# --- Formato del post ---------------------------------------------------------

# Caracteres máximos del resumen en el post (Telegram corta los pies de foto
# en 1024 en total; el resto del presupuesto es para titular y fuente).
SUMMARY_MAX_CHARS = 320

# Texto del botón que lleva a la noticia original.
READ_MORE_LABEL = "Ver más →"
