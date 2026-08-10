"""Agregador de noticias de fútbol -> canal de Telegram.

Lee los feeds de config.FEEDS, descarta lo repetido y lo viejo, y publica las
noticias nuevas con su imagen, un pie de texto y un botón "Ver más" que lleva
al medio original.

    python bot.py --dry-run   # muestra qué publicaría, sin tocar Telegram
    python bot.py             # ejecución real
    python bot.py --stats     # qué se ha publicado y de qué medios
    python bot.py --check     # valida token, canal y feeds
"""
import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

import config
from src import content, db, dedup, feeds, telegram_publisher

log = logging.getLogger("futbol-news")


def is_too_old(article: feeds.Article) -> bool:
    if article.published is None:
        return False  # sin fecha no podemos juzgar; que decida la deduplicación
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MAX_AGE_HOURS)
    return article.published < cutoff


def is_blocked(article: feeds.Article) -> bool:
    haystack = dedup.strip_accents(f"{article.title} {article.summary}".lower())
    return any(word in haystack for word in config.BLOCKLIST)


def select(conn, articles: list[feeds.Article]) -> list[feeds.Article]:
    """Filtra y elige qué se publica en esta pasada.

    Las huellas de titular de lo elegido se van acumulando sobre las del
    historial, así que dos noticias iguales de medios distintos no pueden colarse
    juntas en la misma ejecución.
    """
    known_keys = db.recent_title_keys(conn)
    chosen: list[feeds.Article] = []

    # De más nueva a más vieja: si hay que dejar cosas fuera, que sean las viejas.
    for article in reversed(articles):
        if len(chosen) >= config.MAX_POSTS_PER_RUN:
            break
        if is_too_old(article) or is_blocked(article):
            continue
        if db.seen(conn, article.guid, article.link):
            continue
        key = dedup.title_key(article.title)
        if dedup.is_duplicate(key, known_keys):
            log.debug("Repetida, se descarta: %s", article.title)
            continue
        if not article.image and config.SCRAPE_OG_IMAGE:
            article.image = feeds.scrape_og_image(article.link)
        if not article.image and not config.POST_WITHOUT_IMAGE:
            continue
        known_keys.append(key)
        chosen.append(article)

    # Publicamos de la más antigua a la más reciente: en el canal la última
    # noticia queda arriba, que es como se lee.
    return list(reversed(chosen))


def run(dry_run: bool) -> int:
    conn = db.connect()
    articles = feeds.fetch_all()
    if not articles:
        log.error("Ningún feed devolvió noticias")
        return 1

    chosen = select(conn, articles)
    log.info("%d noticias candidatas de %d leídas", len(chosen), len(articles))
    if not chosen:
        log.info("Nada nuevo que publicar")
        return 0

    for i, article in enumerate(chosen):
        text = content.build(article, with_image=bool(article.image))
        if dry_run:
            print("─" * 60)
            print(f"[{article.source}] imagen: {article.image or 'NINGUNA'}")
            print(text)
            print(f"[{config.READ_MORE_LABEL}] -> {article.link}")
            continue

        envio = telegram_publisher.publish(text, article.link, article.image)
        if envio.reintentable:
            # Consta que no se publicó: la noticia sigue siendo candidata en la
            # siguiente ejecución.
            log.error("No se pudo publicar: %s", article.title)
            continue

        if envio.incierto:
            # Se perdió la respuesta y el post pudo llegar igualmente. Se anota
            # como publicada: perder una noticia es mucho más barato que
            # repetirla en el canal.
            log.warning(
                "Respuesta perdida al publicar «%s»: se da por publicada", article.title
            )
        else:
            log.info("Publicada [%s] %s", article.source, article.title)

        db.record(
            conn,
            source=article.source,
            guid=article.guid,
            link=article.link,
            title=article.title,
            title_key=dedup.title_key(article.title),
            message_id=envio.message_id,
        )
        if i < len(chosen) - 1:
            time.sleep(config.SECONDS_BETWEEN_POSTS)

    if not dry_run:
        removed = db.prune(conn)
        if removed:
            log.debug("Historial purgado: %d filas", removed)
    conn.close()
    return 0


def show_stats() -> int:
    conn = db.connect()
    rows = db.stats(conn)
    if not rows:
        print("Todavía no se ha publicado nada.")
        return 0
    print(f"{'Medio':<20}{'Posts':>7}   Última publicación")
    for row in rows:
        print(f"{row['source']:<20}{row['n']:>7}   {row['ultima'][:16].replace('T', ' ')}")
    print(f"\nTotal: {sum(r['n'] for r in rows)} noticias en los últimos "
          f"{config.DEDUP_WINDOW_DAYS} días")
    conn.close()
    return 0


def check() -> int:
    ok = True
    title = telegram_publisher.check()
    if title:
        print(f"[OK]  Telegram: publicando en «{title}»")
    else:
        print("[ERR] Telegram: revisa TELEGRAM_BOT_TOKEN / TELEGRAM_CHANNEL en .env")
        ok = False

    for source, url in config.FEEDS:
        articles = feeds.fetch(source, url)
        if articles:
            con_imagen = sum(1 for a in articles if a.image)
            print(f"[OK]  {source:<18} {len(articles):>3} noticias, "
                  f"{con_imagen} con imagen  ({url})")
        else:
            print(f"[ERR] {source:<18}   0 noticias  ({url})")
            ok = False
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="muestra los posts por pantalla sin publicarlos")
    parser.add_argument("--stats", action="store_true",
                        help="resumen de lo publicado")
    parser.add_argument("--check", action="store_true",
                        help="comprueba el bot, el canal y los feeds")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.stats:
        return show_stats()
    if args.check:
        return check()
    return run(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
