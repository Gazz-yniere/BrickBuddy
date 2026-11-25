"""Réglages de l'application : les options enregistrées sur l'écran « Paramètres »
   passent devant celles du fichier .env, et les clés ne sont jamais journalisées."""
from . import db
import os

# Options modifiables sur l'écran « Paramètres » ; l'ordre est celui du formulaire.
SETTING_FIELDS = ("REBRICKABLE_API_KEY", "BRICKOWL_API_KEY", "SHOW_PRICES")
# Une clé est un secret : elle ne sort jamais dans un journal ni dans un message.
SECRET_FIELDS = frozenset({"REBRICKABLE_API_KEY", "BRICKOWL_API_KEY"})
# Un case-à-coche décide seul : « décoché » veut dire « désactivé », pas « revenir au .env ».
BOOL_FIELDS = frozenset({"SHOW_PRICES"})
TRUE_WORDS = {"1", "true", "yes", "on"}


def setting(name):
    """Valeur enregistrée dans la base locale pour une option ; vide si rien est enregistré."""
    with db.database() as connection:
        row = connection.execute(
            "SELECT value FROM app_settings WHERE name = ?", (name,)
        ).fetchone()
    return (row["value"] if row else "").strip()


def setting_value(name):
    """Valeur effective d'une option : la base locale d'abord, le fichier .env ensuite."""
    return setting(name) or os.environ.get(name, "").strip()


def flag(name):
    """Option booléenne (SHOW_PRICES) : ce que la base enregistre, sinon le .env."""
    return setting_value(name).casefold() in TRUE_WORDS


def save_settings(values):
    """
    Enregistre les options saisies sur l'écran « Paramètres ».

    Une clé laissée vide est retirée de la base : l'option revient à celle du .env.
    Un case-à-coche est toujours enregistré, coché ou décoché.
    """
    with db.database() as connection:
        for name in SETTING_FIELDS:
            if name in BOOL_FIELDS:
                connection.execute(
                    """
                    INSERT INTO app_settings (name, value) VALUES (?, ?)
                    ON CONFLICT(name) DO UPDATE SET value = excluded.value
                    """,
                    (name, "1" if values.get(name) else "0"),
                )
                continue
            value = (values.get(name) or "").strip()
            if not value:
                connection.execute("DELETE FROM app_settings WHERE name = ?", (name,))
                continue
            connection.execute(
                """
                INSERT INTO app_settings (name, value) VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value
                """,
                (name, value),
            )
