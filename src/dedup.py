"""Detección de noticias repetidas.

El caso difícil no es releer el mismo feed (eso lo resuelve el guid), sino que
Marca, Sport y MD cuenten el mismo fichaje con titulares distintos. Para eso
reducimos cada titular a su "huella": minúsculas, sin acentos, sin palabras
vacías y con los términos ordenados, de forma que "Doblete de Mbappé en el
Bernabéu" y "Mbappé firma un doblete en el Bernabéu" acaben casi idénticos.
"""
import re
import unicodedata

import config

# Palabras vacías y ruido de titulares deportivos: no distinguen una noticia
# de otra, así que las quitamos antes de comparar.
STOPWORDS = {
    "a", "al", "ante", "as", "con", "contra", "cuando", "de", "del", "desde",
    "donde", "e", "el", "ella", "ellos", "en", "entre", "era", "es", "esta",
    "este", "esto", "ha", "hace", "hasta", "hay", "la", "las", "le", "les",
    "lo", "los", "mas", "me", "mi", "mientras", "muy", "no", "o", "para",
    "pero", "por", "porque", "que", "se", "segun", "ser", "si", "sin", "sobre",
    "son", "su", "sus", "tras", "un", "una", "uno", "unos", "y", "ya",
    "directo", "video", "foto", "fotos", "asi", "todo", "todos",
}

WORD_RE = re.compile(r"[a-z0-9ñ]+")

# Con titulares muy cortos hasta el solape de palabras se dispara: "Una puerta
# se abre para Godin" y "Nkunku abre la puerta" comparten dos de tres palabras
# sin tener nada que ver. Por debajo de este número de palabras significativas
# usamos la métrica estricta (Jaccard) en lugar de la generosa (Dice).
MIN_TOKENS_FOR_DICE = 4


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokens(title: str) -> list[str]:
    """Palabras significativas del titular, normalizadas."""
    text = strip_accents(title.lower())
    # Los medios cuelgan secciones al titular con | o -: "Real Madrid | LaLiga".
    text = text.replace("|", " ")
    words = WORD_RE.findall(text)
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


def title_key(title: str) -> str:
    """Huella comparable del titular (tokens únicos, ordenados)."""
    return " ".join(sorted(set(tokens(title))))


def similarity(key_a: str, key_b: str) -> float:
    """0-1. Cuánto vocabulario significativo comparten dos titulares.

    Se mide por palabras y no por caracteres a propósito: comparar cadenas letra
    a letra da parecidos altos entre titulares que solo comparten terminaciones
    ("Giráldez: pretemporada de crecimiento" contra "El Brentford, segundo rival
    en la pretemporada"), y lo que nos interesa es justo lo contrario, que
    coincidan los nombres propios.

    Dice (2·comunes / total) es indulgente con que un medio adorne el titular
    con tres palabras de más, que es exactamente lo que hacen. Para titulares
    cortos se usa Jaccard, más exigente, porque ahí cada palabra pesa demasiado.
    """
    if not key_a or not key_b:
        return 0.0
    set_a, set_b = set(key_a.split()), set(key_b.split())
    common = len(set_a & set_b)
    if min(len(set_a), len(set_b)) < MIN_TOKENS_FOR_DICE:
        return common / len(set_a | set_b)
    return 2 * common / (len(set_a) + len(set_b))


def is_duplicate(key: str, known_keys: list[str]) -> bool:
    """¿Se parece la huella a alguna ya publicada por encima del umbral?"""
    return any(
        similarity(key, known) >= config.TITLE_SIMILARITY for known in known_keys
    )
