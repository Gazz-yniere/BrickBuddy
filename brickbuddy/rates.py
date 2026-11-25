"""Taux de change livres → euros : relevé automatiquement une fois par jour."""
from . import config
from . import db
from .flask_app import app
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request

# Service public sans clé API : le taux GBP → EUR y est publié gratuitement.
# Le reste du projet appelle l'Internet avec urllib : aucune dépendance ajoutée.
RATE_ENDPOINT = "https://open.er-api.com/v6/latest/GBP"
RATE_TIMEOUT = 10
RATE_REFRESH_SECONDS = 24 * 3600
RATE_LOCK_SECONDS = 15 * 60


def rate_payload():
    """Réponse du service de change (bouchonnée dans les tests, jamais appelée en test)."""
    request = urllib.request.Request(RATE_ENDPOINT, headers={"User-Agent": "BrickBuddy/1.0"})
    with urllib.request.urlopen(request, timeout=RATE_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_rate(payload):
    """Taux GBP → EUR lu dans la réponse du service ; None si la réponse est incohérente."""
    try:
        rate = float(payload["rates"]["EUR"])
    except (TypeError, KeyError, ValueError):
        return None
    return rate if rate > 0 else None


def rate_summary(payload):
    """Ce que le journal garde du relevé : le taux, rien de sensible."""
    rate = extract_rate(payload)
    return f"GBP → EUR {rate:.3f}" if rate else "réponse sans taux exploitable"


def stored_state():
    """Taux enregistré, date du dernier relevé, verrou du relevé en cours."""
    with db.database() as connection:
        return connection.execute(
            "SELECT rate, fetched_at, running_since FROM exchange_rate WHERE id = 1"
        ).fetchone()


def current_rate():
    """
    Taux livres → euros en service : le dernier relevé, sinon le .env, sinon le par défaut.

    Le relevé automatique ne bloque jamais l'affichage : sans relevé, on convertit avec
    le taux du .env, ou le taux par défaut.
    """
    state = stored_state()
    rate = float(state["rate"]) if state and state["rate"] else 0.0
    if rate > 0:
        return rate
    try:
        configured = float(os.environ.get("PRICE_GBP_EUR_RATE", ""))
    except (TypeError, ValueError):
        return config.DEFAULT_GBP_EUR_RATE
    return configured if configured > 0 else config.DEFAULT_GBP_EUR_RATE


def mark_rate_refreshed():
    """Horodate le dernier relevé du taux, réussi ou non : un service injoignable
       n'est pas redemandé à chaque affichage de page."""
    with db.database() as connection:
        connection.execute("UPDATE exchange_rate SET fetched_at = ? WHERE id = 1", (time.time(),))


def refresh_rate():
    """Relève le taux et l'enregistre ; un service injoignable garde le taux connu."""
    try:
        payload = rate_payload()
    except (OSError, ValueError) as error:
        app.logger.warning("Change : taux GBP → EUR indisponible (%s)", error)
        mark_rate_refreshed()
        return None
    mark_rate_refreshed()
    rate = extract_rate(payload)
    if not rate:
        app.logger.warning("Change : %s", rate_summary(payload))
        return None
    with db.database() as connection:
        connection.execute("UPDATE exchange_rate SET rate = ? WHERE id = 1", (rate,))
    app.logger.info("Change : taux relevé · %s", rate_summary(payload))
    return rate


def run_rate_refresh():
    try:
        refresh_rate()
    except (OSError, ValueError, sqlite3.Error) as error:
        app.logger.warning("Change : relevé du taux interrompu (%s)", error)
    finally:
        with db.database() as connection:
            connection.execute("UPDATE exchange_rate SET running_since = 0 WHERE id = 1")


def refresh_now():
    """Relève le taux pendant la requête en cours (bouton des paramètres) : la
       réponse confirme le résultat, et le verrou est libéré avant la réponse."""
    state = stored_state()
    if state is None or (state["running_since"] and time.time() - state["running_since"] < RATE_LOCK_SECONDS):
        return None
    with db.database() as connection:
        connection.execute("UPDATE exchange_rate SET running_since = ? WHERE id = 1", (time.time(),))
    try:
        return refresh_rate()
    finally:
        with db.database() as connection:
            connection.execute("UPDATE exchange_rate SET running_since = 0 WHERE id = 1")


def claim_rate_refresh(force=False):
    """Réserve le relevé du taux et le lance en arrière-plan ; False si déjà lancé."""
    state = stored_state()
    if state is None:
        return False
    if state["running_since"] and time.time() - state["running_since"] < RATE_LOCK_SECONDS:
        return False
    if (
        not force
        and state["fetched_at"]
        and time.time() - state["fetched_at"] < RATE_REFRESH_SECONDS
    ):
        return False
    with db.database() as connection:
        connection.execute("UPDATE exchange_rate SET running_since = ? WHERE id = 1", (time.time(),))
    threading.Thread(target=run_rate_refresh, daemon=True).start()
    return True


def request_rate_refresh():
    """Lance le relevé du taux au premier affichage de la journée, en arrière-plan."""
    claim_rate_refresh()


def rate_refresh_running():
    """True pendant qu'un relevé du taux tourne (verrou posé depuis moins de 15 min)."""
    state = stored_state()
    running_since = state["running_since"] if state else 0
    return bool(running_since) and time.time() - running_since <= RATE_LOCK_SECONDS


def rate_refresh_date():
    """Date du dernier relevé réussi du taux, affichée aux utilisateurs ; vide sans taux."""
    state = stored_state()
    if not state or not state["rate"] or not state["fetched_at"]:
        return ""
    return time.strftime("%d/%m/%Y", time.localtime(state["fetched_at"]))


def format_rate(rate):
    """Taux écrit à la française : « 1,240 » pour 1,24 livres par euro."""
    return format(float(rate), ".3f").replace(".", ",")
