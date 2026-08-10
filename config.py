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
# (nombre, url) o (nombre, url, filtro) — el filtro es un trozo de ruta que la
# URL de la noticia debe contener. Solo hace falta en feeds generalistas: el de
# Relevo mezcla fútbol con MotoGP, natación y boxeo, y sin filtrar acabarían en
# el canal. Todos están comprobados y traen imagen en el 100% de las entradas.
FEEDS = [
    ("Marca", "https://e00-marca.uecdn.es/rss/futbol/primera-division.xml"),
    ("Marca", "https://e00-marca.uecdn.es/rss/futbol/champions-league.xml"),
    ("Marca", "https://e00-marca.uecdn.es/rss/futbol/mas-futbol.xml"),
    ("Mundo Deportivo", "https://www.mundodeportivo.com/feed/rss/futbol"),
    ("Mundo Deportivo", "https://www.mundodeportivo.com/feed/rss/futbol/fichajes"),
    ("Sport", "https://www.sport.es/es/rss/futbol/rss.xml"),
    ("AS", "https://as.com/rss/futbol/primera.xml"),
    ("AS", "https://as.com/rss/futbol/internacional.xml"),
    # Relevo es la casa de Matteo Moretto, el socio español de Fabrizio Romano
    # en el mercado de fichajes. Su único RSS que funciona es generalista, de
    # ahí el filtro; el de /rss/futbol/ devuelve XML mal formado.
    ("Relevo", "https://www.relevo.com/rss/", "/futbol/"),
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
# "en directo" saca los minuto a minuto y los liveblogs del mercado de
# fichajes, que los medios reescriben cada hora y llenarían el canal.
BLOCKLIST = ["horoscopo", "quiniela", "en directo", "minuto a minuto"]

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

# Caracteres máximos del resumen en el post. El techo real lo pone Telegram,
# que corta los pies de foto en 1024 contando titular y pie de fuente, así que
# subir esto de ~850 no sirve de nada.
# Cuánto texto hay disponible de verdad, medido en los feeds: AS publica el
# artículo entero (2.600 de media), Sport ~550, Mundo Deportivo ~320 y Marca
# apenas ~100. Los posts de Marca seguirán siendo cortos porque su feed no da
# más de sí.
SUMMARY_MAX_CHARS = 800

# Pie de atribución. Sin enlace a la noticia, esto es lo único que dice de
# dónde sale la información.
VIA_LABEL = "🗞 Vía:"

# --- Emojis del titular -------------------------------------------------------

# El post se encabeza con un emoji elegido según lo que cuenta la noticia. Se
# comparan palabras sueltas contra el titular (en minúsculas y sin acentos) y
# gana la PRIMERA regla que encaje, así que el orden importa: lo más específico
# arriba. Añade o quita palabras con libertad, es una simple lista.
# Las palabras se comparan ENTERAS, no como fragmentos: si no, "precio" pica
# en "Precioso" y "gol" en "golpe". Por eso hay que listar las variantes
# (singular y plural, masculino y femenino) que quieras cazar.
EMOJI_RULES = [
    (("lesion", "lesiones", "lesionado", "lesionada", "lesiona", "rotura",
      "operado", "operacion", "recaida", "molestias"), "🚑"),
    (("oficial", "oficiales", "oficialmente", "confirma", "confirmado",
      "ultima hora"), "🚨"),
    (("ficha", "fichaje", "fichajes", "fichar", "firma", "firmar", "firmado",
      "traspaso", "cesion", "cedido", "renueva", "renovar", "renovacion",
      "acuerdo", "oferta", "ofertas"), "✍️"),
    (("quiere", "interes", "interesa", "pretende", "sondea", "gusta", "suena",
      "negocia", "puja", "pujar", "objetivo"), "👀"),
    (("gol", "goles", "golazo", "doblete", "goleada", "golea", "remontada",
      "remonta", "victoria", "vence", "gana", "derrota", "empate",
      "empata"), "⚽"),
    (("campeon", "campeona", "titulo", "trofeo", "final", "champions",
      "mundial", "eurocopa", "copa"), "🏆"),
    (("polemica", "estalla", "critica", "guerra", "bronca", "tension",
      "enfado", "explota", "escandalo"), "🔥"),
    (("debut", "debuta", "presentacion", "presentado", "estreno",
      "estrena"), "🎬"),
    # Ojo con "vuelve" a secas: en "Francia vuelve a estrellarse" significa
    # "otra vez", no un regreso. Solo cuentan las formas que van a un sitio.
    (("regresa", "regreso", "retorno", "vuelve al", "vuelve a la",
      "de vuelta"), "🔙"),
    (("calendario", "horario", "horarios", "fecha", "fechas", "jornada",
      "sorteo", "donde ver"), "📅"),
    # "once" a secas no vale: pica en "reaparece once meses después".
    (("convocatoria", "convocado", "alineacion", "onces", "once titular",
      "entrenador", "tecnico", "banquillo", "plantilla", "dorsal",
      "dorsales"), "📋"),
    (("millones", "salario", "sueldo", "precio", "clausula"), "💰"),
    (("entrenamiento", "entrena", "pretemporada", "amistoso", "gira"), "🏋️"),
    (("dice", "asegura", "admite", "reconoce", "responde", "avisa", "declara",
      "entrevista", "rueda de prensa"), "🎙️"),
]

# Muchos titulares no son más que una frase entrecomillada de alguien. Eso no
# lo detecta ninguna palabra suelta, así que se mira aparte: si el titular
# lleva una cita entre comillas dobles (las simples no valen, los medios las
# usan para apodos: el 'Cholo', la 'pedrea'), se marca como declaración.
# Se comprueba DESPUÉS de las reglas de arriba: si la cita habla de un fichaje,
# manda el fichaje. Déjalo en "" para desactivarlo.
EMOJI_QUOTE = "🎙️"

# Emoji cuando no encaja ninguna regla.
EMOJI_DEFAULT = "⚽"

# --- Banderas de los clubes ---------------------------------------------------

# Cuando una noticia cruza fronteras (un fichaje del PSG al Liverpool) el post
# se encabeza con las banderas de los dos países en vez de con el emoji de
# tema. Solo se hace con DOS O MÁS países distintos: una noticia de LaLiga con
# un 🇪🇸 delante no aporta nada, y saldría en la mitad de los posts.
#
# El orden importa: se buscan por palabras enteras y de arriba abajo, así que
# "Inter Miami" tiene que ir antes que "Inter".
CLUB_FLAGS = [
    ("🏴󠁧󠁢󠁥󠁮󠁧󠁿", ("liverpool", "manchester city", "manchester united", "chelsea",
            "arsenal", "tottenham", "newcastle", "aston villa", "everton",
            "west ham", "brighton", "brentford", "fulham", "crystal palace",
            "nottingham", "leeds", "wolverhampton", "premier league")),
    ("🇫🇷", ("psg", "paris saint-germain", "marsella", "monaco", "lyon",
            "lille", "niza", "rennes", "ligue 1")),
    # "inter" a secas se queda fuera aposta: chocaba con el Inter Miami. El
    # Inter de Milán se caza igual por "milan".
    ("🇮🇹", ("juventus", "milan", "napoles", "napoli", "roma", "lazio",
            "atalanta", "fiorentina", "serie a")),
    ("🇩🇪", ("bayern", "borussia", "dortmund", "leipzig", "leverkusen",
            "stuttgart", "eintracht", "bundesliga")),
    ("🇵🇹", ("benfica", "oporto", "porto", "braga")),
    ("🇳🇱", ("ajax", "psv", "feyenoord")),
    ("🇸🇦", ("al nassr", "al hilal", "al ittihad", "al ahli")),
    ("🇺🇸", ("inter miami", "galaxy", "lafc")),
    ("🇦🇷", ("boca", "river plate")),
    ("🇧🇷", ("flamengo", "palmeiras", "corinthians", "santos")),
    ("🇪🇸", ("real madrid", "barcelona", "barca", "atletico", "sevilla",
            "betis", "valencia", "villarreal", "athletic", "real sociedad",
            "celta", "espanyol", "getafe", "osasuna", "girona", "rayo",
            "mallorca", "alaves", "elche", "levante", "oviedo", "laliga")),
]

# Noticias donde cualquier emoji llamativo queda fuera de lugar: en estos feeds
# salen muertes, accidentes y funerales con la misma naturalidad que un fichaje.
# Si el titular contiene alguna de estas palabras, el post va sin emoji.
EMOJI_NONE = [
    "muere", "muerte", "fallece", "fallecid", "luto", "funeral", "entierro",
    "sepelio", "accidente", "atropell", "agresion", "agrede", "racismo",
    "racista", "denuncia", "juicio", "carcel", "prision", "condena",
    "detenido", "abusos", "violencia", "cancer", "enfermedad", "uci",
]
