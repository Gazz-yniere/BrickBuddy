"""Prix de l'inventaire : relève quotidienne, file, marqueurs."""
from . import brickowl
from . import config
from . import db
from . import rates
from . import settings
from .flask_app import app
import re
import sqlite3
import threading
import time

# --- Prix des pièces -------------------------------------------------------
# L'API Rebrickable n'expose aucun prix (sa documentation renvoie explicitement
# vers BrickLink et BrickOwl) : la source des prix est donc l'API BrickOwl,
# relevée une fois par jour et gardée dans la base locale.
PRICE_REFRESH_SECONDS = 24 * 3600



PRICE_REFRESH_LOCK_SECONDS = 30 * 60



PRICE_MISSING_RETRY_SECONDS = 30 * 24 * 3600



PRICE_REFRESH_LOG_EVERY = 25



DEFAULT_GBP_EUR_RATE = config.DEFAULT_GBP_EUR_RATE



# Pages d'inventaire Rebrickable dont on tire les références BrickOwl, set par set.
PRICE_BOID_SET_LIMIT = 300



# Rebrickable range les figurines sous la couleur 0 : elles n'ont pas de prix.
MINIFIG_COLOR_ID = 0



def prices_enabled():
    """L'affichage des prix demande l'option SHOW_PRICES et une clé BrickOwl."""
    return settings.flag("SHOW_PRICES") and bool(settings.setting_value("BRICKOWL_API_KEY"))



def gbp_to_eur(amount):
    """Convertit un prix BrickOwl (livres) en euros avec le taux en service."""
    return round(float(amount) * rates.current_rate(), 2)



@app.template_filter("price_eur")
def price_eur(amount):
    """Prix en euros au format français : 1 234 €, 3,50 €."""
    if amount is None:
        return ""
    value = float(amount)
    text = f"{round(value):d}" if value >= 100 else f"{value:.2f}"
    whole, _, decimals = text.partition(".")
    groups = re.findall(r".{1,3}", whole[::-1])
    whole = "\u202f".join(group[::-1] for group in reversed(groups))
    return f"{whole}{',' + decimals if decimals else ''} €"



def remember_brickowl_boids(connection, parts):
    """
    Mémorise les références BrickOwl publiées par Rebrickable, source direct des prix.

    Une pièce importée d'un set dont la référence n'est pas publiée est notée
    « connue sans référence » (« boid » vide) : la relève la laisse de côté au
    lieu de la payer une requête Rebrickable à chaque passage.
    """
    rows = [
        (part["part_num"], int(part.get("color_id") or 0), part.get("brickowl_boid") or "")
        for part in parts
        if part.get("item_type") != "minifig"
        and int(part.get("color_id") or 0) != MINIFIG_COLOR_ID
    ]
    if not rows:
        return
    connection.executemany(
        """
        INSERT INTO part_boids (part_num, color_id, boid)
        VALUES (?, ?, ?)
        ON CONFLICT(part_num, color_id) DO UPDATE SET boid = excluded.boid
        """,
        rows,
    )



def sets_needing_boids(connection):
    """Sets dont l'inventaire n'a pas encore livré ses références BrickOwl."""
    return connection.execute(
        """
        SELECT DISTINCT s.set_num
        FROM sets s
        JOIN set_parts p ON p.set_id = s.id
        LEFT JOIN part_boids b
            ON b.part_num = p.part_num AND b.color_id = p.color_id
        WHERE p.item_type != 'minifig'
              AND p.color_id != 0
              AND b.part_num IS NULL
              AND (s.in_collection = 1 OR s.in_gathering = 1)
        ORDER BY s.set_num
        """
    ).fetchall()



def refresh_known_boids(connection):
    """
    Complète les références BrickOwl connues pour les sets importés, set par set.

    Une page d'inventaire par set suffit pour ses mille premières pièces : aucune
    référence n'est demandée une par une. Une page ratée laisse les autres sets
    continuer et prévient l'hébergeur.
    """
    targets = sets_needing_boids(connection)
    if not targets:
        return 0
    app.logger.info("Rebrickable : %d set(s) sans références BrickOwl connues.", len(targets))
    resolved = 0
    for row in targets:
        set_num = row["set_num"]
        try:
            boids, rows = brickowl.fetch_set_boids(set_num)
        except (RuntimeError, ValueError):
            app.logger.warning(
                "Rebrickable : références BrickOwl du set %s indisponibles.", set_num
            )
            continue
        if boids:
            connection.executemany(
                """
                INSERT INTO part_boids (part_num, color_id, boid)
                VALUES (?, ?, ?)
                ON CONFLICT(part_num, color_id) DO UPDATE SET boid = excluded.boid
                """,
                [(part_num, color_id, boid) for (part_num, color_id), boid in boids.items()],
            )
        # Les pièces de ce set sans référence publiée sont notées « connue sans prix »,
        # et ne repasseront plus par Rebrickable lors des prochaines relèves. Un
        # inventaire qui ne répond pas (aucune pièce lue) ne reçoit aucun marqueur.
        if rows:
            unknown = connection.execute(
                """
                SELECT p.part_num, p.color_id
                FROM set_parts p JOIN sets s ON s.id = p.set_id
                WHERE s.set_num = ? AND p.item_type != 'minifig' AND p.color_id != 0
                """,
                (set_num,),
            ).fetchall()
            connection.executemany(
                """
                INSERT INTO part_boids (part_num, color_id, boid)
                VALUES (?, ?, '')
                ON CONFLICT(part_num, color_id) DO NOTHING
                """,
                [(part["part_num"], int(part["color_id"] or 0)) for part in unknown],
            )
        resolved += len(boids)
        app.logger.info(
            "Rebrickable : %d référence(s) BrickOwl ajoutée(s) pour le set %s.",
            len(boids),
            set_num,
        )
    connection.commit()
    return resolved



def price_targets(connection):
    """
    Références possédées dont le prix est inconnu ou vieux de plus d'un jour.

    Les références connues sans référence BrickOwl (« boid » vide) sont exclues :
    elles ne peuvent pas être relevées, et les envoyer à BrickOwl ferait payer une
    requête Rebrickable chacune.
    """
    cutoff = time.time() - PRICE_REFRESH_SECONDS
    rows = connection.execute(
        """
        SELECT wanted.part_num, wanted.color_id, COALESCE(b.boid, p.boid, '') AS boid
        FROM (
            SELECT part_num, color_id FROM stock_parts
            UNION
            SELECT sp.part_num, sp.color_id
            FROM set_parts sp JOIN sets s ON s.id = sp.set_id
            WHERE s.in_collection = 1 OR s.in_gathering = 1
        ) AS wanted
        LEFT JOIN part_boids b
            ON b.part_num = wanted.part_num AND b.color_id = wanted.color_id
        LEFT JOIN part_prices p
            ON p.part_num = wanted.part_num AND p.color_id = wanted.color_id
        WHERE (p.part_num IS NULL OR p.fetched_at < ?)
              AND (b.part_num IS NULL OR b.boid != '')
        ORDER BY wanted.part_num, wanted.color_id
        """,
        (cutoff,),
    ).fetchall()
    return [(row["part_num"], int(row["color_id"] or 0), row["boid"] or "") for row in rows]



def record_part_price(part_num, color_id, boid, price):
    """Enregistre un prix relevé ; un prix absent est repousse d'un mois."""
    now = time.time()
    # Un prix relevé à 0 est un « pas de prix » : la référence est trop rare chez
    # les vendeurs, on ne la redemande pas chaque jour.
    fetched_at = now if price else now + (PRICE_MISSING_RETRY_SECONDS - PRICE_REFRESH_SECONDS)
    with db.database() as connection:
        connection.execute(
            """
            INSERT INTO part_prices (part_num, color_id, boid, price_gbp, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(part_num, color_id) DO UPDATE SET
                boid = excluded.boid,
                price_gbp = excluded.price_gbp,
                fetched_at = excluded.fetched_at
            """,
            (part_num, color_id, boid, float(price or 0), fetched_at),
        )



def refresh_part_prices(limit=None):
    """Relève les prix de tout l'inventaire chez BrickOwl, une fois par jour au plus.

    Toutes les références possédées sont relevées dans la même course ; la limite
    ne sert qu'à raccourcir une course dans les tests.
    """
    with db.database() as connection:
        # Les pièces importées d'un set n'ont pas toutes leur référence BrickOwl en
        # base : on la demande une fois par set, jamais une fois par pièce.
        refresh_known_boids(connection)
        targets = price_targets(connection)
        if limit:
            targets = targets[:limit]
    if not targets:
        mark_prices_refreshed()
        app.logger.info("BrickOwl : aucun prix à relever")
        return 0
    app.logger.info("BrickOwl : relève de %d références, commencée", len(targets))
    saved = 0
    unknown = 0
    for index, (part_num, color_id, cached_boid) in enumerate(targets, start=1):
        try:
            boid = cached_boid or brickowl.lookup_brickowl_boid(part_num, color_id)
        except (RuntimeError, ValueError) as error:
            app.logger.warning("Relève des prix interrompue : %s", error)
            break
        if not boid:
            # Référence jamais publiée chez BrickOwl : rien à relever. La marqueur
            # « connue sans référence » la garde hors de la file, sans prix en base.
            unknown += 1
            with db.database() as connection:
                connection.execute(
                    """
                    INSERT INTO part_boids (part_num, color_id, boid)
                    VALUES (?, ?, '')
                    ON CONFLICT(part_num, color_id) DO NOTHING
                    """,
                    (part_num, color_id),
                )
                connection.commit()
            continue
        try:
            price = brickowl.extract_brickowl_price(brickowl.brickowl_get("catalog/price_history", {"boid": boid}))
        except LookupError:
            record_part_price(part_num, color_id, boid, 0)
            unknown += 1
            continue
        except (RuntimeError, ValueError) as error:
            app.logger.warning("Relève des prix interrompue : %s", error)
            break
        record_part_price(part_num, color_id, boid, price)
        saved += 1
        if index % PRICE_REFRESH_LOG_EVERY == 0:
            app.logger.info("BrickOwl : relève des prix %d/%d", index, len(targets))
    mark_prices_refreshed()
    app.logger.info(
        "BrickOwl : relève terminée · %d prix relevés, %d références sans prix",
        saved,
        unknown,
    )
    return saved



def mark_prices_refreshed():
    """Horodate la dernière relève des prix."""
    with db.database() as connection:
        connection.execute(
            "UPDATE price_refresh_state SET last_refresh_date = ?, running_since = 0 WHERE id = 1",
            (time.strftime("%Y-%m-%d"),),
        )



def prices_refreshed_today():
    """True si une relève des prix a déjà eu lieu aujourd'hui."""
    with db.database() as connection:
        row = connection.execute(
            "SELECT last_refresh_date FROM price_refresh_state WHERE id = 1"
        ).fetchone()
    return bool(row and row["last_refresh_date"] == time.strftime("%Y-%m-%d"))



def run_price_refresh(limit=None):
    try:
        refresh_part_prices(limit)
    except (RuntimeError, ValueError, OSError, sqlite3.Error) as error:
        app.logger.warning("Relève des prix interrompue : %s", error)
    finally:
        with db.database() as connection:
            connection.execute("UPDATE price_refresh_state SET running_since = 0 WHERE id = 1")



def claim_price_refresh(force=False):
    """Réserve la relève des prix et la lance en arrière-plan ; False si déjà lancée."""
    with db.database() as connection:
        state = connection.execute(
            "SELECT last_refresh_date, running_since FROM price_refresh_state WHERE id = 1"
        ).fetchone()
        if state is None:
            return False
        stale_lock = (
            state["running_since"]
            and time.time() - state["running_since"] > PRICE_REFRESH_LOCK_SECONDS
        )
        if state["running_since"] and not stale_lock:
            return False
        if force:
            # Le bouton force une relève : on efface l'horodatage du jour pour
            # qu'elle reparte vraiment au lieu de ne rien relever.
            connection.execute(
                "UPDATE price_refresh_state SET last_refresh_date = '', running_since = ? WHERE id = 1",
                (time.time(),),
            )
        else:
            if state["last_refresh_date"] == time.strftime("%Y-%m-%d"):
                return False
            connection.execute(
                "UPDATE price_refresh_state SET running_since = ? WHERE id = 1", (time.time(),)
            )
    threading.Thread(target=run_price_refresh, daemon=True).start()
    return True



def request_price_refresh():
    """Lance la relève des prix au premier affichage de la journée, en arrière-plan."""
    if prices_enabled() and not prices_refreshed_today():
        claim_price_refresh()



def price_refresh_running():
    """True pendant qu'une relève des prix tourne (verrou posé depuis moins de 30 min)."""
    with db.database() as connection:
        row = connection.execute(
            "SELECT running_since FROM price_refresh_state WHERE id = 1"
        ).fetchone()
    running_since = row["running_since"] if row else 0
    return bool(running_since) and time.time() - running_since <= PRICE_REFRESH_LOCK_SECONDS



def load_price_map(connection):
    """Prix unitaires en euros, par (référence, couleur), pour les prix connus."""
    rate = rates.current_rate()
    return {
        (row["part_num"], int(row["color_id"] or 0)): round(float(row["price_gbp"]) * rate, 2)
        for row in connection.execute(
            "SELECT part_num, color_id, price_gbp FROM part_prices WHERE price_gbp > 0"
        ).fetchall()
    }



def price_refresh_date():
    """Date du dernier relevé de prix, affichée aux utilisateurs."""
    with db.database() as connection:
        row = connection.execute(
            "SELECT last_refresh_date FROM price_refresh_state WHERE id = 1"
        ).fetchone()
    raw = (row["last_refresh_date"] if row else "") or ""
    if not raw:
        return ""
    try:
        year, month, day = raw.split("-")
        return f"{day}/{month}/{year}"
    except ValueError:
        return raw
