# futbol-news

Agregador de noticias de fútbol: lee los RSS de Marca, Mundo Deportivo, Sport y
AS, descarta lo repetido y publica lo nuevo en el canal de Telegram **Zona
Mixta** con la imagen del propio RSS, un pie de texto y un botón *Ver más* que
lleva a la noticia original en el medio.

## Puesta en marcha

Ya está todo configurado y comprobado. Si empiezas de cero en otro equipo:

```powershell
cd futbol-news
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # y rellena el token de @BotFather
```

El bot (`@zona_mixta_bot`) tiene que ser **administrador del canal con permiso
para publicar**. El canal va por id numérico en `.env` porque es privado: la
Bot API no resuelve el alias `@zona_mixta_es` mientras no sea público.

## Uso

```powershell
python bot.py --check     # valida token, canal y los 7 feeds
python bot.py --dry-run   # enseña los posts por pantalla, sin publicar
python bot.py             # ejecución real
python bot.py --stats     # qué se ha publicado y de qué medios
```

## Cómo evita repetir noticias

Tres filtros encadenados, de más barato a más caro:

1. **Mismo `guid` o mismo enlace** (`src/db.py`): la misma pieza releída del
   mismo feed. Los enlaces se normalizan antes de comparar, quitando `utm_*` y
   demás parámetros de tracking.
2. **Titulares parecidos** (`src/dedup.py`): el caso de verdad, que es Marca,
   Sport y MD contando el mismo fichaje con palabras distintas. Cada titular se
   reduce a su vocabulario significativo (sin acentos, sin palabras vacías,
   ordenado) y se compara con lo publicado en los últimos `DEDUP_WINDOW_DAYS`.
3. **Dentro de la misma ejecución**: lo ya elegido entra en la comparación, así
   que dos versiones de la misma noticia no pueden colarse juntas.

El umbral `TITLE_SIMILARITY` está calibrado contra 426 titulares reales
descargados de los siete feeds: a 0.56 detecta las 12 repeticiones que había
sin marcar ni una noticia distinta. Si alguna vez ves una repetida en el canal,
bájalo un par de centésimas; si notas que se come noticias buenas, súbelo.

La comparación es por palabras y no por caracteres a propósito. Comparar
cadenas letra a letra daba falsos positivos como *"Una puerta se abre para
Godin"* contra *"Nkunku abre la puerta"*: se parecen como texto y no tienen
nada que ver. Lo que importa es que coincidan los nombres propios.

## Qué se publica y cómo

- **Imagen**: la del RSS. Los siete feeds la traen en el 100% de las entradas.
  Se busca en `media:content` (la resolución mayor), `media:thumbnail`,
  los `enclosure` y, si no, en el `<img>` incrustado en el resumen. Si aun así
  no hay, se entra en la noticia a por la `og:image`.
- **Texto**: un emoji, el titular en negrita, el resumen del propio feed
  recortado a `SUMMARY_MAX_CHARS`, y el medio de origen. Si el resumen no es
  más que el titular repetido (pasa en algunos feeds), se omite.
- **Emoji**: se elige según lo que cuenta el titular (`EMOJI_RULES` en
  [config.py](config.py)): 🚑 lesiones, ✍️ fichajes, 👀 rumores, 🏆 títulos,
  📅 horarios... Sobre 426 titulares reales, algo menos de la mitad cae en
  alguna categoría y el resto lleva ⚽.

  Dos cosas de las que no conviene fiarse al editar esas listas. Las palabras
  se comparan **enteras**: con fragmentos, "precio" picaba en *"Precioso"* y
  "once" en *"reaparece once meses después"*. Y hay palabras cuyo sentido
  cambia con la frase: "vuelve" parecía buen indicador de regreso hasta que
  apareció *"Francia vuelve a estrellarse"*, donde significa "otra vez"; por
  eso ahí solo valen las formas que van a un sitio (`vuelve al`, `regresa`).

  Las noticias de luto y sucesos (`EMOJI_NONE`) van **sin emoji**. Estos feeds
  mezclan fichajes con muertes y accidentes con toda naturalidad, y un 🔥
  encima de un obituario es de las pocas cosas capaces de hundir un canal.
- **Botón**: *Ver más →* apuntando a la URL original. Todo el tráfico va al
  medio, que es lo que corresponde: aquí no se reproduce el artículo, solo el
  titular y la entradilla que el propio medio publica en abierto en su RSS.

Si Telegram no consigue descargar la imagen (algunos CDN bloquean el hotlinking)
el bot se la descarga y la sube como fichero; y si tampoco, publica la noticia
como mensaje de texto en vez de perderla.

## Ritmo de publicación

Con `MAX_POSTS_PER_RUN = 3` y la tarea cada 30 minutos salen unas 144 noticias
al día, que es mucho para un canal. Ajusta las dos cosas a la vez: el intervalo
de la tarea programada y el tope por ejecución.

`MAX_AGE_HOURS = 12` evita que la primera ejecución vomite noticias de hace
meses (los feeds de AS, por ejemplo, arrastran piezas de 2022).

## Dónde corre: GitHub Actions

El bot se ejecuta en GitHub Actions cada 30 minutos, así que publica esté el PC
encendido o no. El workflow está en
[.github/workflows/publicar.yml](.github/workflows/publicar.yml).

Dos detalles importantes de cómo funciona ahí:

- **El historial viaja en el repo.** Cada ejecución arranca en una máquina
  limpia que se destruye al terminar, así que `news.db` está versionado a
  propósito y el propio workflow lo vuelve a guardar con un commit. Sin eso el
  bot no recordaría nada y repetiría noticias cada media hora.
- **El token va como *secret***, nunca en el código. En `Settings > Secrets and
  variables > Actions` del repositorio:
  - `TELEGRAM_BOT_TOKEN` — el token de @BotFather
  - `TELEGRAM_CHANNEL` — el id del canal

GitHub no garantiza la puntualidad de las tareas programadas: en horas punta se
retrasan unos minutos y alguna se salta. Para un canal de noticias es
irrelevante.

Para lanzarlo a mano sin esperar al turno: pestaña **Actions > Publicar
noticias > Run workflow**.

### No ejecutar los dos a la vez

`install-task.ps1` registra la misma automatización en el Programador de tareas
de Windows. Servía cuando el bot corría en local, y **no debe estar activa a la
vez que GitHub Actions**: son dos historiales distintos, así que cada uno
publicaría por su cuenta noticias que el otro ya ha publicado. Para quitarla:

```powershell
Unregister-ScheduledTask -TaskName "futbol-news" -Confirm:$false
```

## Añadir o quitar medios

Todo está en `FEEDS`, en [config.py](config.py). Usa siempre feeds de la
sección de fútbol: los generalistas de un diario deportivo meten NBA, tenis y
motor en el canal. Después de tocarlo, `python bot.py --check` te dice si el
feed nuevo responde y si trae imágenes.

Relevo se quedó fuera porque su único RSS que funciona
(`https://www.relevo.com/rss/`) es generalista; el de fútbol devuelve XML mal
formado.
