"""Socle commun des tests : app, base temporaire, bouchons et helpers réutilisés.

Les fichiers test_*.py héritent de SuiteTests : ils partagent la base temporaire,
la session déjà authentifiée et les bouchons Rebrickable / BrickOwl.
"""
import csv
import io
import json
import logging
import os
import re
import tempfile
import time
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

# Les tests ne doivent jamais toucher la base personnelle : la base de test est
# créée avant l'import de l'app, qui initialise le schéma au démarrage.
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "legolist.db")

import app as legolist
from brickbuddy import (
    assets,
    auth,
    brickowl,
    colors,
    config,
    db,
    exports,
    images,
    instructions,
    inventory,
    prices,
    rebrickable,
)
from brickbuddy.flask_app import app


class ImmediateThread:
    """Fil qui s'exécute dans le test : la relève des prix devient déterministe."""

    def __init__(self, target=None, **_kwargs):
        self.target = target

    def start(self):
        if self.target:
            self.target()


class SilentThread:
    """Fil qui ne démarre pas : la page est testée sans relève des prix."""

    def __init__(self, target=None, **_kwargs):
        pass

    def start(self):
        pass


class FakeBrickOwlResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


PRICE_HISTORY = {
    "current_total_amount_all": "87",
    "current_total_amount_new": "81",
    "current_total_amount_used": "6",
    "2year_average_all": "0.03",
    "6months_average_all": "0.00",
    "current_average_all": "0.42",
    "current_average_new": "0.40",
    "current_average_used": "0.51",
    "current_max_all": "0.956",
    "current_min_all": "0.04",
    "current_total_lots_all": "10",
}


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.api_key_patcher = patch.dict(
            "os.environ",
            {
                "REBRICKABLE_API_KEY": "",
                "APP_PASSWORD": "test-password-123",
                # Le .env du poste de développement ne doit jamais piloter les tests.
                "SHOW_PRICES": "",
                "BRICKOWL_API_KEY": "",
                "PRICE_GBP_EUR_RATE": "",
            },
        )
        self.api_key_patcher.start()
        self.addCleanup(brickowl.BRICKOWL_COLOR_CACHE.update, {"fetched_at": 0.0, "ids": {}})
        # Un test ne démarre jamais un vrai fil, donc jamais d'appel réseau : la relève
        # du taux et celle des prix sont muettes par défaut. Les tests qui ont besoin de
        # la relève posent eux-mêmes ImmediateThread.
        self.thread_patcher = patch.object(legolist.threading, "Thread", SilentThread)
        self.thread_patcher.start()
        self.addCleanup(self.thread_patcher.stop)
        self.path_patcher = patch.object(db, "DATABASE_PATH", self.db_path)
        self.path_patcher.start()
        legolist.initialize_database()
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-session-secret-key-that-is-long-enough",
            SESSION_COOKIE_SECURE=False,
        )
        self.client = app.test_client()
        with self.client.session_transaction() as browser_session:
            browser_session["authenticated"] = True
            browser_session["auth_version"] = auth.authentication_version()
            browser_session["csrf_token"] = "test-csrf-token"

    def tearDown(self):
        self.path_patcher.stop()
        self.api_key_patcher.stop()
        self.temp_dir.cleanup()

    def add_set_and_part(self):
        response = self.client.post("/sets", data={"set_num": "10312"})
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            set_id = connection.execute("SELECT id FROM sets").fetchone()["id"]
        response = self.client.post(
            f"/sets/{set_id}/parts",
            data={
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": "4",
                "color_name": "Rouge",
                "quantity": "3",
            },
        )
        self.assertEqual(response.status_code, 302)
        return set_id

    def add_stock_part(
        self,
        part_num,
        color_id=4,
        quantity=1,
        part_name=None,
        color_name="Rouge",
        image_url="",
        item_type="part",
    ):
        response = self.client.post(
            "/stock",
            data={
                "part_num": part_num,
                "part_name": part_name or f"Pièce {part_num}",
                "color_id": str(color_id),
                "color_name": color_name,
                "quantity": str(quantity),
                "image_url": image_url,
                "item_type": item_type,
            },
        )
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            row = connection.execute(
                """
                SELECT id, part_num, color_id, quantity FROM stock_parts
                WHERE part_num = ? AND color_id = ?
                """,
                (part_num, color_id),
            ).fetchone()
        self.assertIsNotNone(row)
        return row

    def create_gathering_set(self, set_num="31145"):
        response = self.client.post(
            "/sets",
            data={"set_num": set_num, "title": f"Set {set_num}"},
        )
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT id, set_num FROM sets WHERE set_num = ?",
                (f"{set_num}-1",),
            ).fetchone()
        self.assertIsNotNone(row)
        return row["id"]

    def create_collected_set(self, set_num="75192"):
        response = self.client.post(
            "/sets",
            data={"set_num": set_num, "return_to": "sets"},
        )
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT id, set_num, in_collection FROM sets WHERE set_num = ?",
                (f"{set_num}-1",),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["in_collection"], 1)
        return row["id"]

    def insert_set_part(
        self,
        set_id,
        part_num,
        color_id=4,
        quantity=1,
        missing_quantity=None,
        part_name=None,
        color_name="Rouge",
    ):
        if missing_quantity is None:
            missing_quantity = quantity
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name,
                     quantity, missing_quantity, image_url, item_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, '', 'part')
                """,
                (
                    set_id,
                    part_num,
                    part_name or f"Pièce {part_num}",
                    color_id,
                    color_name,
                    quantity,
                    missing_quantity,
                ),
            )

    # --- Prix des pièces : source BrickOwl, relevée une fois par jour ---
    price_env = {
        "SHOW_PRICES": "true",
        "BRICKOWL_API_KEY": "cle-brickowl",
        "PRICE_GBP_EUR_RATE": "1.5",
    }

    def own_a_part(self, part_num="3001", color_id="4", quantity="3"):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        with legolist.database() as connection:
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (set_id,)
            ).fetchone()["id"]
        # La pièce est marquée trouvée : elle entre dans l'inventaire.
        self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "sets", "missing_quantity": "0"},
        )
        return set_id

    def record_price(self, part_num, color_id, price_gbp, boid="", fetched_at=None):
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO part_prices (part_num, color_id, boid, price_gbp, fetched_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (part_num, color_id, boid, price_gbp, fetched_at if fetched_at is not None else time.time()),
            )

    def name_part_color(self, color_name):
        """Aligne le nom de couleur de la pièce possédée sur un nom Rebrickable."""
        with legolist.database() as connection:
            connection.execute("UPDATE set_parts SET color_name = ?", (color_name,))
            connection.execute("UPDATE stock_parts SET color_name = ?", (color_name,))

    @contextmanager

    def capture_logs(self):
        """Capture les lignes du journal de l'application le temps du bloc."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger = app.logger
        previous_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            yield lambda: stream.getvalue()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

    def fake_rebrickable_lookup(self, calls=None):
        """Rebrickable bouchonné : la pièce 3001 et la couleur 4 telles que publiées."""

        def getter(path):
            if calls is not None:
                calls.append(("rebrickable", path))
            if path.startswith("colors/"):
                return {
                    "results": [
                        {"id": 4, "name": "Red", "external_ids": {"BrickOwl": {"ext_ids": [81]}}},
                        {"id": 1, "name": "Blue", "external_ids": {"BrickOwl": {"ext_ids": [39]}}},
                    ]
                }
            return {
                "part_num": "3001",
                "name": "Brick 2 x 4",
                "external_ids": {"BrickOwl": ["771344"]},
            }

        return getter
