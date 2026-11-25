"""Prix des pièces.

Chaque test pilote l'app par son client de test, sur une base temporaire.
"""

from unittest.mock import patch
import csv
import io
import time
import xml.etree.ElementTree as ET
from brickbuddy import brickowl
from brickbuddy import prices
from brickbuddy import rebrickable
import app as legolist
import urllib.error
from testbase import FakeBrickOwlResponse
from testbase import ImmediateThread
from testbase import PRICE_HISTORY
from testbase import SilentThread
from testbase import SuiteTests

class PrixTests(SuiteTests):
    def test_bricklink_and_brickowl_exports_aggregate_piece_quantities(self):
        self.add_set_and_part()
        with legolist.database() as connection:
            set_id = connection.execute("SELECT id FROM sets").fetchone()["id"]
        self.client.post(
            f"/sets/{set_id}/parts",
            data={"part_num": "3001", "color_id": "4", "color_name": "Rouge", "quantity": "2"},
        )

        bricklink = ET.fromstring(self.client.get("/export/bricklink.xml").data)
        item = bricklink.find("ITEM")
        self.assertEqual(item.findtext("ITEMID"), "3001")
        self.assertEqual(item.findtext("COLOR"), "4")
        self.assertEqual(item.findtext("MINQTY"), "5")

        brickowl_rows = list(csv.reader(io.StringIO(self.client.get("/export/brickowl.csv").data.decode("utf-8"))))
        self.assertEqual(brickowl_rows, [["ItemNo", "Color", "Qty"], ["3001", "4", "5"]])

    def test_fetch_set_inventory_captures_brickowl_references(self):
        inventory_page = {
            "results": [
                {
                    "part": {
                        "part_num": "3001",
                        "name": "Brique 2 x 4",
                        "external_ids": {"BrickOwl": ["771344"]},
                    },
                    "color": {
                        "id": 4,
                        "name": "Rouge",
                        "external_ids": {"BrickOwl": {"ext_ids": [81]}},
                    },
                    "quantity": 2,
                },
                {
                    "part": {"part_num": "3002", "name": "Plaque"},
                    "color": {"id": 4, "name": "Rouge"},
                    "quantity": 1,
                },
            ],
            "next": None,
        }
        with patch.object(rebrickable, "fetch_set_info", return_value={"name": "Set"}):
            with patch.object(rebrickable, "rebrickable_get", return_value=inventory_page):
                _, parts = rebrickable.fetch_set_inventory("10312")

        by_num = {part["part_num"]: part for part in parts}
        self.assertEqual(by_num["3001"]["brickowl_boid"], "771344-81")
        self.assertEqual(by_num["3002"]["brickowl_boid"], "")

    def test_adding_a_set_caches_its_brickowl_references(self):
        imported_parts = [
            {
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": 4,
                "color_name": "Rouge",
                "quantity": 3,
                "image_url": "",
                "brickowl_boid": "771344-81",
            }
        ]
        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
    rebrickable,
    "fetch_set_inventory",
                return_value=(
                    {"name": "Set importé", "theme_id": 22, "set_img_url": "", "year": 2020},
                    imported_parts,
                ),
            ):
                with patch.object(rebrickable, "fetch_theme_name", return_value="Creator"):
                    with patch.object(
    rebrickable, "fetch_minifig_parts_for_set", return_value=[]
                    ):
                        self.client.post("/sets", data={"set_num": "10312", "return_to": "sets"})

        with legolist.database() as connection:
            row = connection.execute(
                "SELECT part_num, color_id, boid FROM part_boids"
            ).fetchone()
        self.assertEqual((row["part_num"], row["color_id"], row["boid"]), ("3001", 4, "771344-81"))

    def test_prices_are_hidden_without_the_option(self):
        self.own_a_part()
        page = self.client.get("/inventaire")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"stat-tile-price", page.data)
        self.assertNotIn(b"alloc-price", page.data)
        self.assertNotIn(b"stat-tile-note", page.data)

    def test_prices_need_both_the_option_and_the_key(self):
        self.assertFalse(prices.prices_enabled())
        with patch.dict(
            "os.environ", {"SHOW_PRICES": "true", "BRICKOWL_API_KEY": ""}, clear=False
        ):
            self.assertFalse(prices.prices_enabled())
        with patch.dict(
            "os.environ",
            {"SHOW_PRICES": "false", "BRICKOWL_API_KEY": "cle-brickowl"},
            clear=False,
        ):
            self.assertFalse(prices.prices_enabled())
        with patch.dict("os.environ", self.price_env, clear=False):
            self.assertTrue(prices.prices_enabled())

    def test_inventory_shows_unit_price_line_total_and_the_total_value(self):
        self.own_a_part()
        self.record_price("3001", 4, 2.0)
        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
            legolist.threading, "Thread", SilentThread
        ):
            page = self.client.get("/inventaire")
        self.assertEqual(page.status_code, 200)
        # 2,00 £ × 1,5 = 3,00 € l'unité, × 3 pièces = 9,00 €.
        self.assertIn(b"3,00 \xe2\x82\xac l\xe2\x80\x99unit\xc3\xa9", page.data)
        self.assertIn(b"<strong>9,00 \xe2\x82\xac</strong>", page.data)
        self.assertIn(b"stat-tile-price", page.data)
        self.assertIn(b"valeur estim\xc3\xa9e", page.data)
        self.assertIn(b"1 r\xc3\xa9f\xc3\xa9rence sur 1 avec un prix", page.data)

    def test_parts_without_a_known_price_show_nothing(self):
        self.own_a_part()
        self.record_price("3001", 4, 0)
        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
            legolist.threading, "Thread", SilentThread
        ):
            page = self.client.get("/inventaire")
        self.assertIn(b"stat-tile-price", page.data)
        self.assertIn(b"0,00 \xe2\x82\xac", page.data)
        self.assertNotIn(b"alloc-price", page.data)
        self.assertIn(b"0 r\xc3\xa9f\xc3\xa9rences sur 1 avec un prix", page.data)

    def test_price_refresh_runs_once_per_day_and_caches_the_price(self):
        self.own_a_part()
        calls = []

        def fake_brickowl_get(path, params=None):
            calls.append((path, dict(params or {})))
            return dict(PRICE_HISTORY)

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", fake_brickowl_get
        ), patch.object(
    rebrickable, "rebrickable_get", self.fake_rebrickable_lookup()
        ), patch.object(legolist.threading, "Thread", ImmediateThread):
            self.client.get("/inventaire")

        # La référence BrickOwl vient de Rebrickable : pièce 771344, couleur 81 (Rouge).
        self.assertEqual(calls, [("catalog/price_history", {"boid": "771344-81"})])
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT boid, price_gbp FROM part_prices WHERE part_num = '3001'"
            ).fetchone()
            state = connection.execute(
                "SELECT last_refresh_date, running_since FROM price_refresh_state WHERE id = 1"
            ).fetchone()
        self.assertEqual((row["boid"], row["price_gbp"]), ("771344-81", 0.42))
        self.assertEqual(state["last_refresh_date"], time.strftime("%Y-%m-%d"))
        self.assertEqual(state["running_since"], 0)

        calls.clear()
        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", fake_brickowl_get
        ), patch.object(
    rebrickable, "rebrickable_get", self.fake_rebrickable_lookup()
        ), patch.object(legolist.threading, "Thread", ImmediateThread):
            self.client.get("/inventaire")
        self.assertEqual(calls, [])

    def test_set_parts_use_the_brickowl_reference_published_by_rebrickable(self):
        self.own_a_part()
        with legolist.database() as connection:
            connection.execute(
                "INSERT INTO part_boids (part_num, color_id, boid) VALUES ('3001', 4, '771344-81')"
            )
        calls = []

        def fake_brickowl_get(path, params=None):
            calls.append((path, dict(params or {})))
            return dict(PRICE_HISTORY)

        def no_rebrickable(path):
            raise AssertionError("La référence connue ne doit pas être redemandée.")

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", fake_brickowl_get
        ), patch.object(rebrickable, "rebrickable_get", no_rebrickable), patch.object(
            legolist.threading, "Thread", ImmediateThread
        ):
            self.client.get("/inventaire")
        self.assertEqual(calls, [("catalog/price_history", {"boid": "771344-81"})])
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT boid, price_gbp FROM part_prices WHERE part_num = '3001'"
            ).fetchone()
        self.assertEqual((row["boid"], row["price_gbp"]), ("771344-81", 0.42))

    def test_a_price_of_zero_is_not_reshown_and_not_reshasked(self):
        self.own_a_part()
        calls = []

        def fake_brickowl_get(path, params=None):
            calls.append((path, dict(params or {})))
            # Réponse relevée sur une référence rare : aucun prix chez les vendeurs.
            return dict(
                PRICE_HISTORY,
                current_average_all="0.00",
                current_average_new="0.00",
                current_average_used="0.00",
                current_min_all="0",
                current_total_lots_all="0",
            )

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", fake_brickowl_get
        ), patch.object(
    rebrickable, "rebrickable_get", self.fake_rebrickable_lookup()
        ), patch.object(legolist.threading, "Thread", ImmediateThread):
            self.client.get("/inventaire")

        with legolist.database() as connection:
            row = connection.execute(
                "SELECT price_gbp, fetched_at FROM part_prices WHERE part_num = '3001'"
            ).fetchone()
            # Le relevé du jour est repoussé d'un mois : il ne sera pas redemandé.
            pending = prices.price_targets(connection)
        self.assertEqual(row["price_gbp"], 0)
        self.assertGreater(row["fetched_at"], time.time())
        self.assertEqual(pending, [])

    def test_price_refresh_survives_a_network_failure(self):
        self.own_a_part()
        with legolist.database() as connection:
            connection.execute(
                "INSERT INTO part_boids (part_num, color_id, boid) VALUES ('3001', 4, '771344-81')"
            )

        def failing_brickowl_get(path, params=None):
            raise RuntimeError("Impossible de joindre BrickOwl. Vérifiez votre connexion.")

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", failing_brickowl_get
        ), patch.object(legolist.threading, "Thread", ImmediateThread):
            page = self.client.get("/inventaire")
        self.assertEqual(page.status_code, 200)
        with legolist.database() as connection:
            stored = connection.execute("SELECT COUNT(*) AS n FROM part_prices").fetchone()["n"]
            state = connection.execute(
                "SELECT running_since FROM price_refresh_state WHERE id = 1"
            ).fetchone()
        self.assertEqual(stored, 0)
        self.assertEqual(state["running_since"], 0)

    def test_price_refresh_lock_blocks_a_second_worker(self):
        self.own_a_part()
        with legolist.database() as connection:
            connection.execute(
                "UPDATE price_refresh_state SET running_since = ? WHERE id = 1", (time.time(),)
            )
        calls = []
        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", lambda path, params=None: calls.append(path)
        ), patch.object(legolist.threading, "Thread", ImmediateThread):
            self.client.get("/inventaire")
        self.assertEqual(calls, [])

    def test_one_run_refreshes_every_owned_reference(self):
        self.own_a_part()
        self.client.post("/stock", data={"part_num": "3004", "color_id": "1", "quantity": "2"})
        calls = []
        rebrickable_calls = []

        def fake_brickowl_get(path, params=None):
            calls.append((path, dict(params or {})))
            return dict(PRICE_HISTORY)

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", fake_brickowl_get
        ), patch.object(
    rebrickable, "rebrickable_get", self.fake_rebrickable_lookup(rebrickable_calls)
        ), patch.object(legolist.threading, "Thread", ImmediateThread):
            self.client.get("/inventaire")
        # Une seule course relève toutes les références possédées, sans plafond.
        self.assertEqual(
            calls,
            [
                ("catalog/price_history", {"boid": "771344-81"}),
                ("catalog/price_history", {"boid": "771344-39"}),
            ],
        )
        # La table des couleurs est commune : une seule demande pour toutes les pièces.
        self.assertEqual(sum(1 for _, path in rebrickable_calls if path.startswith("colors/")), 1)
        with legolist.database() as connection:
            self.assertEqual(prices.price_targets(connection), [])

    def test_price_refresh_stops_when_rebrickable_is_unreachable(self):
        """Sans clé Rebrickable, la relève s'arrête sans inventer un prix à 0."""
        self.own_a_part()

        def fake_brickowl_get(path, params=None):
            raise AssertionError("Aucun prix ne doit être demandé sans BOID.")

        def no_rebrickable(path):
            raise RuntimeError("Ajoutez REBRICKABLE_API_KEY dans le fichier .env.")

        with self.capture_logs() as logged:
            with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", fake_brickowl_get
            ), patch.object(rebrickable, "rebrickable_get", no_rebrickable), patch.object(
                legolist.threading, "Thread", ImmediateThread
            ):
                page = self.client.get("/inventaire")
        self.assertEqual(page.status_code, 200)
        with legolist.database() as connection:
            row = connection.execute("SELECT boid, price_gbp FROM part_prices").fetchone()
            state = connection.execute(
                "SELECT running_since FROM price_refresh_state WHERE id = 1"
            ).fetchone()
            # La référence reste en file : on ne sait pas si elle a un prix chez BrickOwl.
            pending = prices.price_targets(connection)
        self.assertIsNone(row)
        self.assertEqual(state["running_since"], 0)
        self.assertEqual(pending, [("3001", 4, "")])
        self.assertIn("REBRICKABLE_API_KEY", logged())

    def test_price_history_lookup_errors_are_recorded_as_priceless(self):
        self.own_a_part()
        self.name_part_color("Red")

        def fake_brickowl_get(path, params=None):
            if path == "catalog/price_history":
                raise LookupError("Référence inconnue chez BrickOwl.")
            return dict(PRICE_HISTORY)

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", fake_brickowl_get
        ), patch.object(
    rebrickable, "rebrickable_get", self.fake_rebrickable_lookup()
        ), patch.object(legolist.threading, "Thread", ImmediateThread):
            page = self.client.get("/inventaire")
        self.assertEqual(page.status_code, 200)
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT boid, price_gbp, fetched_at FROM part_prices"
            ).fetchone()
            targets = prices.price_targets(connection)
        self.assertEqual((row["boid"], row["price_gbp"]), ("771344-81", 0))
        self.assertGreater(row["fetched_at"], time.time())
        self.assertEqual(targets, [])

    def test_price_refresh_button_starts_a_refresh_after_the_daily_one(self):
        self.own_a_part()
        self.name_part_color("Red")
        with legolist.database() as connection:
            connection.execute(
                "UPDATE price_refresh_state SET last_refresh_date = ? WHERE id = 1",
                (time.strftime("%Y-%m-%d"),),
            )

        def fake_brickowl_get(path, params=None):
            if path == "catalog/price_history":
                return dict(PRICE_HISTORY)
            raise AssertionError("Seul le prix est demandé chez BrickOwl.")

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", fake_brickowl_get
        ), patch.object(
    rebrickable, "rebrickable_get", self.fake_rebrickable_lookup()
        ), patch.object(legolist.threading, "Thread", ImmediateThread):
            page = self.client.post(
                "/parametres/prix/rafraichir", data={"csrf_token": "test-csrf-token"}
            )
            self.assertEqual(page.status_code, 302)
            self.assertIn("/parametres", page.headers["Location"])
            # Le message de confirmation s'affiche sur les paramètres, après la redirection.
            settings_page = self.client.get("/parametres").get_data(as_text=True)
            self.assertIn("Relève des prix lancée", settings_page)
            # La relève forcée a relevé toutes les pièces : la couverture est à jour.
            self.assertIn("prix connu pour 1 référence sur 1", settings_page)
        with legolist.database() as connection:
            price = connection.execute(
                "SELECT price_gbp FROM part_prices WHERE part_num = '3001'"
            ).fetchone()
            state = connection.execute(
                "SELECT running_since FROM price_refresh_state WHERE id = 1"
            ).fetchone()
        # Le relevé forcé passe outre la date du jour et rend la main en fin de course.
        self.assertEqual(price["price_gbp"], 0.42)
        self.assertEqual(state["running_since"], 0)

    def test_price_refresh_button_reports_a_running_refresh(self):
        self.own_a_part()
        with legolist.database() as connection:
            connection.execute(
                "UPDATE price_refresh_state SET running_since = ? WHERE id = 1", (time.time(),)
            )
        started = []

        def fake_thread(target, **kwargs):
            started.append(target)
            return ImmediateThread(target=target, **kwargs)

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
            legolist.threading, "Thread", fake_thread
        ):
            page = self.client.post(
                "/parametres/prix/rafraichir", data={"csrf_token": "test-csrf-token"}
            )
        self.assertEqual(page.status_code, 302)
        self.assertEqual(started, [])
        self.assertIn("déjà en cours", self.client.get("/parametres").get_data(as_text=True))

    def test_the_price_button_lives_on_the_settings_page_only(self):
        self.own_a_part()
        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
            legolist.threading, "Thread", SilentThread
        ):
            inventory_page = self.client.get("/inventaire").get_data(as_text=True)
            settings_page = self.client.get("/parametres").get_data(as_text=True)
        self.assertNotIn("Rafraîchir les prix", inventory_page)
        self.assertIn("Rafraîchir les prix", settings_page)
        self.assertIn("prix connu pour 0 références sur 1", settings_page)

    def test_price_refresh_button_requires_the_form_token(self):
        self.own_a_part()
        with patch.dict("os.environ", self.price_env, clear=False):
            page = self.client.post("/parametres/prix/rafraichir", data={"csrf_token": "wrong"})
        self.assertEqual(page.status_code, 400)

    def test_price_refresh_button_without_the_api_key(self):
        self.own_a_part()
        started = []

        def fake_thread(target, **kwargs):
            started.append(target)
            return ImmediateThread(target=target, **kwargs)

        with patch.dict(
            "os.environ", {"SHOW_PRICES": "true", "BRICKOWL_API_KEY": ""}, clear=False
        ), patch.object(legolist.threading, "Thread", fake_thread):
            page = self.client.post(
                "/parametres/prix/rafraichir",
                data={"csrf_token": "test-csrf-token"},
                follow_redirects=True,
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(started, [])
        self.assertIn("désactivé", page.get_data(as_text=True))

    def test_price_refresh_logs_its_run(self):
        self.own_a_part()
        self.name_part_color("Red")

        def fake_brickowl_get(path, params=None):
            if path == "catalog/price_history":
                return dict(PRICE_HISTORY)
            raise AssertionError("Seul le prix est demandé chez BrickOwl.")

        with self.capture_logs() as logged:
            with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", fake_brickowl_get
            ), patch.object(
    rebrickable, "rebrickable_get", self.fake_rebrickable_lookup()
            ), patch.object(legolist.threading, "Thread", ImmediateThread):
                self.client.get("/inventaire")
        self.assertIn("BrickOwl : relève de 1 références, commencée", logged())
        self.assertIn("relève terminée · 1 prix relevés, 0 références sans prix", logged())

    def test_priceless_references_do_not_starve_the_queue(self):
        """Les références sans prix sont mises de côté, les autres sont toutes relevées."""
        with legolist.database() as connection:
            for index in range(40):
                connection.execute(
                    """INSERT INTO stock_parts (part_num, part_name, color_id, color_name, quantity)
                       VALUES (?, ?, ?, ?, ?)""",
                    (f"3{index:03d}", f"Pièce {index}", 4, "Red", 1),
                )
        known = {f"3{index:03d}" for index in range(30)}

        def lookup_boid(part_num, color_id):
            return "771344-81" if part_num in known else ""

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
    brickowl, "brickowl_get", lambda path, params=None: dict(PRICE_HISTORY)
        ), patch.object(brickowl, "lookup_brickowl_boid", lookup_boid), patch.object(
            legolist.threading, "Thread", ImmediateThread
        ):
            page = self.client.get("/inventaire")
        self.assertEqual(page.status_code, 200)
        with legolist.database() as connection:
            priced = connection.execute(
                "SELECT COUNT(*) AS n FROM part_prices WHERE price_gbp > 0"
            ).fetchone()["n"]
            priceless = connection.execute(
                "SELECT COUNT(*) AS n FROM part_prices WHERE price_gbp = 0"
            ).fetchone()["n"]
            marked = connection.execute(
                "SELECT COUNT(*) AS n FROM part_boids WHERE boid = ''"
            ).fetchone()["n"]
            targets = prices.price_targets(connection)
        # Une seule course pour les 40 références : les 10 sans référence BrickOwl sont
        # marquées « connue sans référence », jamais redemandées, jamais payées en prix 0.
        self.assertEqual((priced, priceless), (30, 0))
        self.assertEqual(marked, 10)
        self.assertEqual(targets, [])

    def test_brickowl_requests_are_logged_without_the_api_key(self):
        def fake_urlopen(req, timeout=None):
            return FakeBrickOwlResponse(dict(PRICE_HISTORY))

        with self.capture_logs() as logged:
            with patch.dict("os.environ", {"BRICKOWL_API_KEY": "cle-test"}, clear=False), patch.object(
                legolist.urllib.request, "urlopen", fake_urlopen
            ):
                brickowl.brickowl_get("catalog/price_history", {"boid": "771344-81"})
        self.assertIn("BrickOwl : catalog/price_history boid=771344-81", logged())
        self.assertNotIn("cle-test", logged())

    def test_brickowl_requests_are_gated_and_authenticated(self):
        seen = []

        def fake_urlopen(req, timeout=None):
            seen.append(req.full_url)
            return FakeBrickOwlResponse({"status": "success", "data": {"price": 1.0}})

        with patch.dict("os.environ", {"BRICKOWL_API_KEY": "cle-test"}, clear=False), patch.object(
            legolist.urllib.request, "urlopen", fake_urlopen
        ):
            payload = brickowl.brickowl_get("catalog/price_history", {"boid": "3001-4"})
            brickowl.brickowl_get("catalog/price_history", {"boid": "3001-4"})
        self.assertEqual(payload["data"]["price"], 1.0)
        self.assertIn("api.brickowl.com/v1/catalog/price_history?", seen[0])
        self.assertIn("boid=3001-4", seen[0])
        self.assertIn("key=cle-test", seen[0])
        with legolist.database() as connection:
            gate = connection.execute(
                "SELECT next_request_at FROM brickowl_request_gate WHERE id = 1"
            ).fetchone()["next_request_at"]
        self.assertGreater(gate, time.time())

    def test_brickowl_errors_are_reported_in_french(self):
        with patch.dict("os.environ", {"BRICKOWL_API_KEY": ""}, clear=False):
            self.assertRaises(RuntimeError, brickowl.brickowl_get, "catalog/list")

        def http_error(code):
            def raiser(req, timeout=None):
                raise urllib.error.HTTPError(
                    "https://api.brickowl.com/v1/catalog/list", code, "Erreur", None, io.BytesIO(b"")
                )

            return raiser

        with patch.dict("os.environ", {"BRICKOWL_API_KEY": "cle-test"}, clear=False):
            with patch.object(legolist.urllib.request, "urlopen", http_error(404)):
                self.assertRaises(LookupError, brickowl.brickowl_get, "catalog/id_lookup")
            with patch.object(legolist.urllib.request, "urlopen", http_error(401)):
                with self.assertRaises(ValueError) as caught:
                    brickowl.brickowl_get("catalog/list")
                self.assertIn("clé BrickOwl", str(caught.exception))
            with patch.object(legolist.urllib.request, "urlopen", http_error(429)):
                with self.assertRaises(RuntimeError) as caught:
                    brickowl.brickowl_get("catalog/price_history", {"boid": "3001-4"})
                self.assertIn("dernière mise à jour", str(caught.exception))

    def test_brickowl_references_are_read_from_rebrickable(self):
        self.assertEqual(brickowl.brickowl_external_id({"BrickOwl": ["771344"]}, "BrickOwl"), "771344")
        self.assertEqual(brickowl.brickowl_external_id({"BrickOwl": {"ext_ids": [81]}}, "BrickOwl"), "81")
        self.assertEqual(brickowl.brickowl_external_id({"BrickOwl": {"ext_ids": [None, 38]}}, "BrickOwl"), "38")
        self.assertEqual(brickowl.brickowl_external_id({"BrickOwl": ["None"]}, "BrickOwl"), "")
        self.assertEqual(brickowl.brickowl_external_id({"BrickOwl": []}, "BrickOwl"), "")
        self.assertEqual(brickowl.brickowl_external_id({}, "BrickOwl"), "")
        self.assertEqual(brickowl.brickowl_external_id(None, "BrickOwl"), "")

    def test_color_table_maps_rebrickable_colors_to_brickowl(self):
        calls = []
        with patch.object(rebrickable, "rebrickable_get", self.fake_rebrickable_lookup(calls)):
            mapping = brickowl.brickowl_color_ids()
        self.assertEqual((mapping[4], mapping[1]), (81, 39))
        self.assertTrue(calls)
        # La table est gardée en mémoire : elle n'est pas redemandée à chaque pièce.
        with patch.object(rebrickable, "rebrickable_get", self.fake_rebrickable_lookup(calls)):
            calls.clear()
            self.assertEqual(brickowl.brickowl_color_ids()[4], 81)
        self.assertEqual(calls, [])

    def test_brickowl_price_parsing_is_tolerant(self):
        self.assertEqual(brickowl.extract_brickowl_price(dict(PRICE_HISTORY)), 0.42)
        self.assertEqual(brickowl.extract_brickowl_price({"data": dict(PRICE_HISTORY)}), 0.42)
        self.assertEqual(brickowl.extract_brickowl_price({"data": {"current_average_new": "2.50"}}), 2.5)
        self.assertEqual(brickowl.extract_brickowl_price({"data": {"current_min_all": 1.1567}}), 1.157)
        self.assertIsNone(brickowl.extract_brickowl_price({"data": {"current_average_all": "0.00"}}))
        self.assertIsNone(brickowl.extract_brickowl_price({"data": {"2year_average_all": "0.03"}}))
        self.assertIsNone(brickowl.extract_brickowl_price({"data": {}}))
        self.assertIsNone(brickowl.extract_brickowl_price({"data": "pas un objet"}))

    def test_prices_are_converted_with_the_env_rate_and_shown_in_french(self):
        with patch.dict("os.environ", {"PRICE_GBP_EUR_RATE": "2"}, clear=False):
            self.assertEqual(prices.gbp_to_eur(2.5), 5.0)
        with patch.dict("os.environ", {"PRICE_GBP_EUR_RATE": "absurde"}, clear=False):
            self.assertEqual(
                prices.gbp_to_eur(1.0), round(1.0 * prices.DEFAULT_GBP_EUR_RATE, 2)
            )
        self.assertEqual(prices.price_eur(None), "")
        self.assertEqual(prices.price_eur(3.5), "3,50 €")
        self.assertEqual(prices.price_eur(1234.0), "1\u202f234 €")
        self.assertEqual(prices.price_eur(12345.6), "12\u202f346 €")

    def test_price_refresh_is_skipped_without_the_option(self):
        self.own_a_part()
        calls = []
        with patch.object(
    brickowl, "brickowl_get", lambda path, params=None: calls.append(path)
        ), patch.object(legolist.threading, "Thread", ImmediateThread):
            self.client.get("/inventaire")
        self.assertEqual(calls, [])
