import csv
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import app as legolist


class LegoListTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.api_key_patcher = patch.dict(
            "os.environ",
            {
                "REBRICKABLE_API_KEY": "",
                "APP_PASSWORD": "test-password-123",
            },
        )
        self.api_key_patcher.start()
        self.path_patcher = patch.object(legolist, "DATABASE_PATH", self.db_path)
        self.path_patcher.start()
        legolist.initialize_database()
        legolist.app.config.update(
            TESTING=True,
            SECRET_KEY="test-session-secret-key-that-is-long-enough",
            SESSION_COOKIE_SECURE=False,
        )
        self.client = legolist.app.test_client()
        with self.client.session_transaction() as browser_session:
            browser_session["authenticated"] = True
            browser_session["auth_version"] = legolist.authentication_version()
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

    def test_login_protects_pages_and_accepts_the_shared_password(self):
        client = legolist.app.test_client()
        protected_page = client.get("/sets?search=castle")
        self.assertEqual(protected_page.status_code, 302)
        self.assertIn("next=/sets?search%3Dcastle", protected_page.location)
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/static/favicon.svg").status_code, 200)
        self.assertEqual(
            client.post("/sets", data={"set_num": "10312"}).status_code, 302
        )

        login_page = client.get("/login?next=https://example.com")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn(b'name="next" value="/pieces"', login_page.data)
        with client.session_transaction() as browser_session:
            csrf_token = browser_session["csrf_token"]

        invalid = client.post(
            "/login",
            data={
                "csrf_token": csrf_token,
                "next": "/sets",
                "password": "wrong-password",
            },
        )
        self.assertEqual(invalid.status_code, 401)
        self.assertIn(b"Mot de passe incorrect", invalid.data)

        valid = client.post(
            "/login",
            data={
                "csrf_token": csrf_token,
                "next": "/sets",
                "password": "test-password-123",
            },
        )
        self.assertEqual(valid.status_code, 302)
        self.assertEqual(valid.location, "/sets")
        cookie = valid.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        with client.session_transaction() as browser_session:
            self.assertTrue(browser_session["authenticated"])
            self.assertTrue(browser_session.permanent)
            csrf_token = browser_session["csrf_token"]

        logout = client.post("/logout", data={"csrf_token": csrf_token})
        self.assertEqual(logout.status_code, 302)
        self.assertEqual(logout.location, "/login")
        self.assertEqual(client.get("/sets").status_code, 302)

    def test_login_accepts_a_unicode_shared_password(self):
        password = "Mot de passe sécurisé 123"
        with patch.dict("os.environ", {"APP_PASSWORD": password}):
            client = legolist.app.test_client()
            client.get("/login")
            with client.session_transaction() as browser_session:
                csrf_token = browser_session["csrf_token"]
            response = client.post(
                "/login",
                data={"csrf_token": csrf_token, "password": password},
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/pieces")

    def test_login_limits_failed_attempts_and_requires_csrf(self):
        client = legolist.app.test_client()
        login_page = client.get("/login")
        self.assertEqual(login_page.status_code, 200)
        with client.session_transaction() as browser_session:
            csrf_token = browser_session["csrf_token"]

        invalid_csrf = client.post(
            "/login", data={"csrf_token": "wrong-token", "password": "test-password"}
        )
        self.assertEqual(invalid_csrf.status_code, 400)
        for _ in range(5):
            response = client.post(
                "/login",
                data={"csrf_token": csrf_token, "password": "wrong-password"},
            )
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.headers["Retry-After"])

        logout_without_csrf = self.client.post("/logout")
        self.assertEqual(logout_without_csrf.status_code, 400)

    def test_password_change_invalidates_existing_sessions(self):
        response = self.client.get("/sets")
        self.assertEqual(response.status_code, 200)
        with patch.dict(
            "os.environ",
            {"APP_PASSWORD": "new-test-password"},
        ):
            response = self.client.get("/sets")
            login_page = self.client.get("/login")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)
        self.assertEqual(login_page.status_code, 200)

    def test_cross_origin_post_is_rejected(self):
        response = self.client.post(
            "/sets",
            data={"set_num": "10312"},
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(response.status_code, 403)
        with legolist.database() as connection:
            set_count = connection.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
        self.assertEqual(set_count, 0)

    def test_login_fails_closed_when_authentication_is_not_configured(self):
        client = legolist.app.test_client()
        with patch.dict("os.environ", {"APP_PASSWORD": ""}):
            response = client.get("/login")
            self.assertEqual(response.status_code, 503)
            self.assertIn(b"connexion n&#39;est pas encore configur", response.data)
            protected = client.get("/pieces")
            self.assertEqual(protected.status_code, 302)

    def test_set_and_parts_are_rendered_and_missing_quantity_can_be_updated(self):
        set_id = self.add_set_and_part()
        page = self.client.get("/pieces")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"3001", page.data)
        self.assertIn(b'class="part-image-label">Brique 2 x 4</span>', page.data)
        self.assertNotIn(b"10312-1", self.client.get("/sets").data)
        self.assertNotIn(b"Brique 2 x 4", self.client.get("/manquantes").data)
        with legolist.database() as connection:
            part_id = connection.execute("SELECT id FROM set_parts").fetchone()["id"]
        self.client.post(f"/parts/{part_id}/missing", data={"missing_quantity": "1"})
        with legolist.database() as connection:
            part = connection.execute(
                "SELECT quantity, missing_quantity FROM set_parts WHERE id = ?", (part_id,)
            ).fetchone()
        self.assertEqual((part["quantity"], part["missing_quantity"]), (3, 1))
        self.client.post(f"/sets/{set_id}/collect")
        self.assertIn(b"10312-1", self.client.get("/sets").data)
        self.assertIn(b"Brique 2 x 4", self.client.get("/manquantes").data)
        response = self.client.post(f"/sets/{set_id}/uncollect")
        self.assertEqual(response.headers["Location"], "/sets")
        self.assertIn(b"10312-1", self.client.get("/pieces").data)
        self.assertNotIn(b"Brique 2 x 4", self.client.get("/manquantes").data)
        with legolist.database() as connection:
            part = connection.execute(
                "SELECT missing_quantity FROM set_parts WHERE id = ?", (part_id,)
            ).fetchone()
        self.assertEqual(part["missing_quantity"], 1)

    def test_pages_aggregate_shared_pieces_and_filter_missing_parts(self):
        first_set_id = self.add_set_and_part()
        self.client.post("/sets", data={"set_num": "31145", "title": "Le dragon rouge"})
        with legolist.database() as connection:
            second_set_id = connection.execute(
                "SELECT id FROM sets WHERE set_num = '31145-1'"
            ).fetchone()["id"]
        self.client.post(
            f"/sets/{second_set_id}/parts",
            data={
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": "4",
                "color_name": "Rouge",
                "quantity": "2",
            },
        )
        self.client.post(
            f"/sets/{first_set_id}/parts",
            data={
                "part_num": "3002",
                "part_name": "Brique 2 x 3",
                "color_id": "11",
                "color_name": "Noir",
                "quantity": "1",
            },
        )

        pieces_page = self.client.get("/pieces")
        self.assertEqual(pieces_page.status_code, 200)
        self.assertIn(b"31145-1", pieces_page.data)
        page_text = pieces_page.get_data(as_text=True)
        self.assertIn("×3", page_text)
        self.assertIn("×2", page_text)

        with legolist.database() as connection:
            complete_part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ? AND part_num = '3002'",
                (first_set_id,),
            ).fetchone()["id"]
        response = self.client.post(
            f"/parts/{complete_part_id}/missing",
            data={"missing_quantity": "0", "return_to": "pieces"},
        )
        self.assertEqual(response.headers["Location"], "/pieces")
        missing_page = self.client.get("/manquantes")
        self.assertEqual(missing_page.status_code, 200)
        self.assertNotIn(b"Brique 2 x 4", missing_page.data)
        self.client.post(f"/sets/{first_set_id}/collect")
        missing_page = self.client.get("/manquantes")
        self.assertIn(b"Brique 2 x 4", missing_page.data)
        self.assertNotIn(b"Brique 2 x 3", missing_page.data)
        remaining_to_gather = self.client.get("/pieces").get_data(as_text=True)
        self.assertIn("31145-1", remaining_to_gather)
        self.assertIn("×2", remaining_to_gather)
        self.assertIn("×3", remaining_to_gather)

    def test_color_sections_show_total_missing_and_collapse_when_complete(self):
        set_id = self.add_set_and_part()
        page = self.client.get("/pieces").get_data(as_text=True)
        self.assertIn('data-color-missing>3</strong>', page)
        self.assertIn('data-color-group data-missing="3" open', page)
        self.assertIn('name="mark_complete"', page)

        with legolist.database() as connection:
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (set_id,)
            ).fetchone()["id"]
        response = self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "pieces", "mark_complete": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["missing"], 0)

    def test_root_redirects_to_pieces_and_pages_are_separate(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/pieces")
        self.assertEqual(self.client.get("/sets").status_code, 200)
        self.assertEqual(self.client.get("/inventaire").status_code, 200)
        self.assertEqual(self.client.get("/manquantes").status_code, 200)

    def test_inventory_aggregates_found_parts_by_color_and_reference(self):
        owned_set_id = self.add_set_and_part()
        self.client.post(f"/sets/{owned_set_id}/collect")
        with legolist.database() as connection:
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (owned_set_id,)
            ).fetchone()["id"]
        self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "sets", "missing_quantity": "1"},
        )
        self.client.post("/sets", data={"set_num": "31146", "title": "Deuxième set"})
        with legolist.database() as connection:
            second_set_id = connection.execute(
                "SELECT id FROM sets WHERE set_num = '31146-1'"
            ).fetchone()["id"]
        self.client.post(
            f"/sets/{second_set_id}/parts",
            data={
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": "4",
                "color_name": "Rouge",
                "quantity": "4",
            },
        )
        self.client.post(f"/sets/{second_set_id}/collect")
        with legolist.database() as connection:
            second_part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (second_set_id,)
            ).fetchone()["id"]
        self.client.post(
            f"/parts/{second_part_id}/missing",
            data={"return_to": "sets", "missing_quantity": "2"},
        )
        unowned_set_response = self.client.post(
            "/sets",
            data={"set_num": "31145", "title": "Set à réunir seulement"},
        )
        self.assertEqual(unowned_set_response.status_code, 302)

        page = self.client.get("/inventaire")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Mon inventaire", page.data)
        self.assertIn(b"Rouge", page.data)
        self.assertIn(b"Brique 2 x 4", page.data)
        self.assertIn(b"R\xc3\xa9f. 3001", page.data)
        self.assertIn(b"\xc3\x974", page.data)
        self.assertNotIn(b'class="inventory-set', page.data)

        filtered_page = self.client.get("/inventaire?color=Rouge&q=3001")
        self.assertEqual(filtered_page.status_code, 200)
        self.assertIn(b"Brique 2 x 4", filtered_page.data)
        self.assertNotIn(b"Inventaire vide", filtered_page.data)

    def test_buildable_page_and_routes_are_removed(self):
        for path in (
            "/sets-constructibles",
            "/sets-constructibles/recherche",
            "/sets-constructibles/analyser",
        ):
            response = (
                self.client.get(path)
                if path == "/sets-constructibles"
                else self.client.post(path)
            )
            self.assertEqual(response.status_code, 404, path)

        page = self.client.get("/pieces")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"Sets constructibles", page.data)

        with legolist.database() as connection:
            cache_tables = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'buildable_%'
                """
            ).fetchall()
        self.assertEqual(cache_tables, [])

    def test_rebrickable_images_are_saved_and_served_from_local_cache(self):
        class FakeHeaders:
            def get_content_type(self):
                return "image/jpeg"

            def get(self, name):
                return str(len(b"\x89PNG\r\n\x1a\nimage data")) if name == "Content-Length" else None

        class FakeImageResponse:
            headers = FakeHeaders()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return "https://cdn.rebrickable.com/media/parts/test.png"

            def read(self, _size):
                return b"\x89PNG\r\n\x1a\nimage data"

        source_url = "https://cdn.rebrickable.com/media/parts/test.png"
        with patch.object(legolist, "IMAGE_CACHE_PATH", Path(self.temp_dir.name) / "images"):
            with legolist.app.test_request_context("/"):
                image_route = legolist.local_image_url(source_url)
                self.assertEqual(legolist.local_image_url(source_url), image_route)
                legolist.app.process_response(legolist.app.response_class())
            with patch.object(
                legolist.urllib.request,
                "urlopen",
                return_value=FakeImageResponse(),
            ) as open_image:
                first = self.client.get(image_route)
                second = self.client.get(image_route)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.data, first.data)
        self.assertEqual(first.mimetype, "image/png")
        self.assertEqual(open_image.call_count, 1)
        with legolist.database() as connection:
            image_count = connection.execute(
                "SELECT COUNT(*) FROM rebrickable_image_cache WHERE source_url = ?",
                (source_url,),
            ).fetchone()[0]
        self.assertEqual(image_count, 1)

    def test_health_endpoint_checks_database_and_returns_json(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_missing_quantity_can_be_set_per_set_from_piece_list(self):
        first_set_id = self.add_set_and_part()
        self.client.post("/sets", data={"set_num": "31145", "title": "Le dragon rouge"})
        with legolist.database() as connection:
            second_set_id = connection.execute(
                "SELECT id FROM sets WHERE set_num = '31145-1'"
            ).fetchone()["id"]
        self.client.post(
            f"/sets/{second_set_id}/parts",
            data={
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": "4",
                "color_name": "Rouge",
                "quantity": "2",
            },
        )
        with legolist.database() as connection:
            first_part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (first_set_id,)
            ).fetchone()["id"]
            second_part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (second_set_id,)
            ).fetchone()["id"]

        page = self.client.get("/pieces")
        self.assertIn(b"set-step-button", page.data)
        self.assertIn(b"part-missing-total", page.data)
        self.assertIn(b'class="parts-grid"', page.data)
        self.assertIn(b'class="piece-card"', page.data)
        self.assertIn(b'class="piece-card-heading"', page.data)
        self.assertIn(b'class="piece-set-list"', page.data)
        self.assertNotIn(b'class="piece-card-name"', page.data)
        self.assertIn(b"Le dragon rouge", page.data)
        self.assertNotIn(b"QUANTIT\xc3\x89 TOTALE", page.data)
        self.assertNotIn(b"\xc3\x80 TROUVER", page.data)
        response = self.client.post(
            f"/parts/{first_part_id}/missing",
            data={"return_to": "pieces", "missing_quantity": "1"},
        )
        self.assertEqual(response.headers["Location"], "/pieces")
        with legolist.database() as connection:
            first_part = connection.execute(
                "SELECT quantity, missing_quantity FROM set_parts WHERE id = ?",
                (first_part_id,),
            ).fetchone()
            second_part = connection.execute(
                "SELECT quantity, missing_quantity FROM set_parts WHERE id = ?",
                (second_part_id,),
            ).fetchone()
        self.assertEqual(first_part["missing_quantity"], 1)
        self.assertEqual(second_part["missing_quantity"], 2)

        self.client.post(
            f"/parts/{first_part_id}/missing",
            data={"return_to": "pieces", "missing_quantity": "0"},
        )
        with legolist.database() as connection:
            first_part = connection.execute(
                "SELECT quantity, missing_quantity FROM set_parts WHERE id = ?",
                (first_part_id,),
            ).fetchone()
        self.assertEqual(first_part["missing_quantity"], 0)
        completed_page = self.client.get("/pieces").get_data(as_text=True)
        self.assertIn('set-status-form is-complete', completed_page)

        self.client.post(
            f"/parts/{first_part_id}/missing",
            data={"return_to": "pieces", "change": "-1"},
        )
        self.client.post(
            f"/parts/{first_part_id}/missing",
            data={"return_to": "pieces", "change": "1"},
        )
        with legolist.database() as connection:
            first_part = connection.execute(
                "SELECT quantity, missing_quantity FROM set_parts WHERE id = ?",
                (first_part_id,),
            ).fetchone()
        self.assertEqual(first_part["missing_quantity"], 1)

        self.client.post(
            f"/parts/{first_part_id}/missing",
            data={"return_to": "pieces", "change": "2"},
        )
        with legolist.database() as connection:
            first_part = connection.execute(
                "SELECT missing_quantity FROM set_parts WHERE id = ?",
                (first_part_id,),
            ).fetchone()
        self.assertEqual(first_part["missing_quantity"], 1)

        self.client.post(
            f"/parts/{first_part_id}/missing",
            data={"return_to": "pieces", "missing_quantity": "0"},
        )
        self.client.post(f"/sets/{first_set_id}/collect")
        self.assertNotIn(
            f'class="set-card" data-set-id="{first_set_id}"'.encode(),
            self.client.get("/pieces").data,
        )
        self.assertIn(b"10312-1", self.client.get("/sets").data)
        self.assertNotIn(b"Brique 2 x 4", self.client.get("/manquantes").data)

    def test_piece_quantity_button_request_returns_json_without_page_redirect(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (set_id,)
            ).fetchone()["id"]

        response = self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "pieces", "change": "-1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertNotIn("Location", response.headers)
        self.assertEqual(
            response.get_json(),
            {
                "missing": 2,
                "quantity": 3,
                "part_missing": 2,
                "total_missing": 2,
                "set_id": set_id,
                "set_missing": 2,
                "gathering_complete": False,
            },
        )

    def test_owned_complete_set_leaves_gather_list(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        with legolist.database() as connection:
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (set_id,)
            ).fetchone()["id"]

        response = self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "pieces", "mark_complete": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["gathering_complete"])
        with legolist.database() as connection:
            statuses = connection.execute(
                "SELECT in_collection, in_gathering FROM sets WHERE id = ?",
                (set_id,),
            ).fetchone()
        self.assertEqual(tuple(statuses), (1, 0))
        self.assertNotIn(
            f'class="set-card" data-set-id="{set_id}"'.encode(),
            self.client.get("/pieces").data,
        )
        self.assertIn(b"10312-1", self.client.get("/sets").data)

    def test_set_can_be_added_directly_to_collection(self):
        response = self.client.post(
            "/sets",
            data={"set_num": "10312", "return_to": "sets"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/sets")
        with legolist.database() as connection:
            statuses = connection.execute(
                "SELECT in_collection, in_gathering FROM sets"
            ).fetchone()
        self.assertEqual(tuple(statuses), (1, 0))
        self.assertIn(b"10312-1", self.client.get("/sets").data)
        self.assertNotIn(
            b'class="set-card" data-set-id="1"',
            self.client.get("/pieces").data,
        )

    def test_collection_sets_are_grouped_into_collapsible_themes(self):
        first_set_id = self.add_set_and_part()
        self.client.post(f"/sets/{first_set_id}/collect")
        second_response = self.client.post(
            "/sets",
            data={
                "set_num": "31145",
                "return_to": "sets",
                "theme_name": "Creator",
            },
        )
        self.assertEqual(second_response.status_code, 302)
        with legolist.database() as connection:
            second_set_id = connection.execute(
                "SELECT id FROM sets WHERE set_num = '31145-1'"
            ).fetchone()["id"]
        self.client.post(
            f"/sets/{second_set_id}/parts",
            data={
                "return_to": "sets",
                "part_num": "3002",
                "part_name": "Plate",
                "color_id": "1",
                "color_name": "Blanc",
                "quantity": "1",
            },
        )

        page = self.client.get("/sets").get_data(as_text=True)
        self.assertIn('class="collection-theme-list"', page)
        self.assertIn('<summary class="collection-theme-summary">', page)
        self.assertIn("Creator", page)
        self.assertIn("Thème non renseigné", page)
        self.assertIn('class="set-card collection-set-card" data-set-id="1"', page)
        self.assertIn('class="set-card collection-set-card" data-set-id="2"', page)

    def test_add_set_fetches_rebrickable_theme_name(self):
        imported_parts = [
            {
                "part_num": "3001",
                "part_name": "Brique",
                "color_id": 4,
                "color_name": "Rouge",
                "quantity": 3,
                "image_url": "",
            }
        ]
        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
                legolist,
                "fetch_set_inventory",
                return_value=(
                    {
                        "name": "Set importé",
                        "theme_id": 22,
                        "set_img_url": "",
                        "year": 2020,
                    },
                    imported_parts,
                ),
            ):
                with patch.object(
                    legolist, "fetch_theme_name", return_value="Creator"
                ) as fetch_theme:
                    response = self.client.post(
                        "/sets",
                        data={"set_num": "10312", "return_to": "sets"},
                    )

        self.assertEqual(response.status_code, 302)
        fetch_theme.assert_called_once_with(22)
        with legolist.database() as connection:
            set_row = connection.execute(
                "SELECT theme_name, year FROM sets"
            ).fetchone()
        self.assertEqual(set_row["theme_name"], "Creator")
        self.assertEqual(set_row["year"], 2020)
        page = self.client.get("/sets").get_data(as_text=True)
        self.assertIn("2020", page)
        self.assertIn("https://rebrickable.com/sets/10312-1/", page)

    def test_direct_collection_add_can_mark_all_parts_found_including_later_manual_parts(self):
        response = self.client.post(
            "/sets",
            data={
                "set_num": "10312",
                "return_to": "sets",
                "all_parts_found": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            set_row = connection.execute(
                "SELECT id, all_parts_found FROM sets"
            ).fetchone()
        self.assertEqual(set_row["all_parts_found"], 1)

        self.client.post(
            f"/sets/{set_row['id']}/parts",
            data={
                "return_to": "sets",
                "part_num": "3001",
                "part_name": "Brique",
                "color_id": "4",
                "color_name": "Rouge",
                "quantity": "3",
            },
        )
        with legolist.database() as connection:
            part = connection.execute(
                "SELECT quantity, missing_quantity FROM set_parts WHERE set_id = ?",
                (set_row["id"],),
            ).fetchone()
        self.assertEqual(tuple(part), (3, 0))

    def test_direct_collection_add_marks_imported_parts_found_when_selected(self):
        imported_parts = [
            {
                "part_num": "3001",
                "part_name": "Brique",
                "color_id": 4,
                "color_name": "Rouge",
                "quantity": 3,
                "image_url": "",
            }
        ]
        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
                legolist,
                "fetch_set_inventory",
                return_value=({"name": "Set importé", "set_img_url": ""}, imported_parts),
            ):
                response = self.client.post(
                    "/sets",
                    data={
                        "set_num": "10312",
                        "return_to": "sets",
                        "all_parts_found": "1",
                    },
                )
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            part = connection.execute(
                "SELECT quantity, missing_quantity FROM set_parts"
            ).fetchone()
        self.assertEqual(tuple(part), (3, 0))

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

        brickowl = list(csv.reader(io.StringIO(self.client.get("/export/brickowl.csv").data.decode("utf-8"))))
        self.assertEqual(brickowl, [["ItemNo", "Color", "Qty"], ["3001", "4", "5"]])

    def test_exports_separate_sets_to_gather_from_owned_sets(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            part_id = connection.execute("SELECT id FROM set_parts").fetchone()["id"]
        self.client.post(
            f"/parts/{part_id}/missing",
            data={"missing_quantity": "1", "return_to": "pieces"},
        )

        gather_xml = ET.fromstring(
            self.client.get("/export/bricklink.xml?scope=gather").data
        )
        self.assertEqual(gather_xml.findtext("ITEM/MINQTY"), "1")
        owned_xml = ET.fromstring(
            self.client.get("/export/bricklink.xml?scope=owned").data
        )
        self.assertEqual(owned_xml.findall("ITEM"), [])

        self.client.post(f"/sets/{set_id}/collect")
        self.client.post(
            f"/sets/{set_id}/gathering",
            data={"in_gathering": "0"},
        )
        self.client.post("/sets", data={"set_num": "31145"})
        with legolist.database() as connection:
            second_set_id = connection.execute(
                "SELECT id FROM sets WHERE set_num = '31145-1'"
            ).fetchone()["id"]
        self.client.post(
            f"/sets/{second_set_id}/parts",
            data={"part_num": "3001", "color_id": "4", "color_name": "Rouge", "quantity": "2"},
        )

        owned_xml = ET.fromstring(
            self.client.get("/export/bricklink.xml?scope=owned").data
        )
        gather_xml = ET.fromstring(
            self.client.get("/export/bricklink.xml?scope=gather").data
        )
        self.assertEqual(owned_xml.findtext("ITEM/MINQTY"), "1")
        self.assertEqual(gather_xml.findtext("ITEM/MINQTY"), "2")

    def test_set_without_parts_cannot_be_added_to_collection(self):
        self.client.post("/sets", data={"set_num": "10312"})
        with legolist.database() as connection:
            set_id = connection.execute("SELECT id FROM sets").fetchone()["id"]

        self.client.post(f"/sets/{set_id}/collect")
        with legolist.database() as connection:
            in_collection = connection.execute(
                "SELECT in_collection FROM sets WHERE id = ?", (set_id,)
            ).fetchone()["in_collection"]
        self.assertEqual(in_collection, 0)
        self.assertNotIn(b'class="set-card"', self.client.get("/sets").data)

    def test_complete_set_parts_marks_every_part_found_only_for_that_set(self):
        first_set_id = self.add_set_and_part()
        self.client.post(
            f"/sets/{first_set_id}/parts",
            data={
                "part_num": "3002",
                "part_name": "Brique 2 x 3",
                "color_id": "11",
                "color_name": "Noir",
                "quantity": "2",
            },
        )
        self.client.post("/sets", data={"set_num": "31145"})
        with legolist.database() as connection:
            second_set_id = connection.execute(
                "SELECT id FROM sets WHERE set_num = '31145-1'"
            ).fetchone()["id"]
        self.client.post(
            f"/sets/{second_set_id}/parts",
            data={
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": "4",
                "color_name": "Rouge",
                "quantity": "4",
            },
        )

        response = self.client.post(f"/sets/{first_set_id}/complete-parts")
        self.assertEqual(response.headers["Location"], "/pieces")
        with legolist.database() as connection:
            first_set_missing = connection.execute(
                "SELECT SUM(missing_quantity) FROM set_parts WHERE set_id = ?",
                (first_set_id,),
            ).fetchone()[0]
            second_set_missing = connection.execute(
                "SELECT SUM(missing_quantity) FROM set_parts WHERE set_id = ?",
                (second_set_id,),
            ).fetchone()[0]
            first_set_collection_status = connection.execute(
                "SELECT in_collection FROM sets WHERE id = ?", (first_set_id,)
            ).fetchone()[0]

        self.assertEqual(first_set_missing, 0)
        self.assertEqual(second_set_missing, 4)
        self.assertEqual(first_set_collection_status, 0)
        page = self.client.get("/pieces").get_data(as_text=True)
        self.assertIn("part-missing-total", page)
        self.assertIn('set-status-form is-complete', page)
        self.assertIn("Tout chercher", page)

        response = self.client.post(f"/sets/{first_set_id}/complete-parts")
        self.assertEqual(response.headers["Location"], "/pieces")
        with legolist.database() as connection:
            first_set_parts = connection.execute(
                "SELECT quantity, missing_quantity FROM set_parts WHERE set_id = ?",
                (first_set_id,),
            ).fetchall()
        self.assertTrue(
            all(part["quantity"] == part["missing_quantity"] for part in first_set_parts)
        )

    def test_owned_set_can_be_added_to_gather_list_without_losing_collection_status(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        self.client.post(
            f"/sets/{set_id}/gathering",
            data={"in_gathering": "0"},
        )
        self.assertNotIn(b'class="piece-card"', self.client.get("/pieces").data)
        response = self.client.post(
            f"/sets/{set_id}/gathering",
            data={"in_gathering": "1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(b"10312-1", self.client.get("/sets").data)
        self.assertIn(b"10312-1", self.client.get("/pieces").data)
        self.assertIn(b"Brique 2 x 4", self.client.get("/manquantes").data)

    def test_same_set_reference_can_be_tracked_as_separate_copies(self):
        first_set_id = self.add_set_and_part()
        self.client.post(f"/sets/{first_set_id}/collect")
        response = self.client.post("/sets", data={"set_num": "10312"})
        self.assertEqual(response.status_code, 302)

        with legolist.database() as connection:
            second_set_id = connection.execute(
                "SELECT id FROM sets WHERE id != ?", (first_set_id,)
            ).fetchone()["id"]
        response = self.client.post(
            f"/sets/{second_set_id}/parts",
            data={
                "part_num": "3002",
                "part_name": "Brique 2 x 3",
                "color_id": "11",
                "color_name": "Noir",
                "quantity": "2",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.client.post(f"/sets/{second_set_id}/collect")
        with legolist.database() as connection:
            copies = connection.execute(
                """
                SELECT s.id, s.in_collection, s.in_gathering,
                       p.quantity, p.missing_quantity
                FROM sets s JOIN set_parts p ON p.set_id = s.id
                WHERE s.set_num = '10312-1'
                ORDER BY s.id
                """
            ).fetchall()
        self.assertEqual(len(copies), 2)
        self.assertEqual(
            [(copy["in_collection"], copy["in_gathering"]) for copy in copies],
            [(1, 1), (1, 1)],
        )
        self.assertEqual(
            [(copy["quantity"], copy["missing_quantity"]) for copy in copies],
            [(3, 3), (2, 2)],
        )
        self.assertIn(b"exemplaire 2", self.client.get("/pieces").data)
        self.assertIn(b"#2", self.client.get("/pieces").data)
        self.assertEqual(
            self.client.get("/sets").data.count(b'class="set-card collection-set-card"'),
            2,
        )

    def test_removing_set_from_gathering_keeps_its_data_without_confirmation(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                "UPDATE sets SET set_image_url = ? WHERE id = ?",
                ("https://example.test/10312.jpg", set_id),
            )
        page = self.client.get("/pieces").data
        self.assertIn(b'class="set-avatar"><img', page)
        self.assertIn(b"https://example.test/10312.jpg", page)

        response = self.client.post(
            f"/sets/{set_id}/gathering",
            data={"in_gathering": "0", "return_to": "pieces"},
        )

        self.assertEqual(response.headers["Location"], "/pieces")
        page = self.client.get("/pieces").data
        self.assertNotIn(f'data-set-id="{set_id}"'.encode(), page)
        self.assertNotIn(b"Supprimer ce set", page)
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT in_gathering FROM sets WHERE id = ?", (set_id,)
            ).fetchone()
            part_count = connection.execute(
                "SELECT COUNT(*) FROM set_parts WHERE set_id = ?", (set_id,)
            ).fetchone()[0]
        self.assertEqual(row["in_gathering"], 0)
        self.assertEqual(part_count, 1)
        self.client.post("/sets", data={"set_num": "10312"})
        self.assertNotIn(b"exemplaire 2", self.client.get("/pieces").data)

    def test_duplicate_set_starts_with_all_its_pieces_to_check(self):
        source_id = self.add_set_and_part()

        response = self.client.post(
            f"/sets/{source_id}/duplicate", data={"return_to": "pieces"}
        )

        self.assertEqual(response.headers["Location"], "/pieces")
        with legolist.database() as connection:
            copies = connection.execute(
                """
                SELECT s.in_collection, s.in_gathering,
                       p.quantity, p.missing_quantity
                FROM sets s JOIN set_parts p ON p.set_id = s.id
                WHERE s.set_num = '10312-1'
                ORDER BY s.id
                """
            ).fetchall()
        self.assertEqual(len(copies), 2)
        self.assertEqual(
            [(row["in_collection"], row["in_gathering"]) for row in copies],
            [(0, 1), (0, 1)],
        )
        self.assertEqual(
            [(row["quantity"], row["missing_quantity"]) for row in copies],
            [(3, 3), (3, 3)],
        )
        self.assertIn(b"exemplaire 2", self.client.get("/pieces").data)

    def test_collection_copy_can_be_completed_without_changing_other_copies(self):
        first_set_id = self.add_set_and_part()
        self.client.post(f"/sets/{first_set_id}/collect")
        self.client.post(
            f"/sets/{first_set_id}/duplicate", data={"return_to": "sets"}
        )
        with legolist.database() as connection:
            second_set_id = connection.execute(
                "SELECT MAX(id) FROM sets"
            ).fetchone()[0]

        response = self.client.post(
            f"/sets/{second_set_id}/complete-parts",
            data={"return_to": "sets"},
        )

        self.assertEqual(response.headers["Location"], "/sets")
        with legolist.database() as connection:
            quantities = connection.execute(
                """
                SELECT s.id, p.missing_quantity
                FROM sets s JOIN set_parts p ON p.set_id = s.id
                ORDER BY s.id
                """
            ).fetchall()
        self.assertEqual(
            [(row["id"], row["missing_quantity"]) for row in quantities],
            [(first_set_id, 3), (second_set_id, 0)],
        )

    def test_selling_collection_copy_removes_only_that_copy_from_inventory(self):
        first_set_id = self.add_set_and_part()
        self.client.post(f"/sets/{first_set_id}/collect")
        with legolist.database() as connection:
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (first_set_id,)
            ).fetchone()["id"]
        self.client.post(
            f"/parts/{part_id}/missing",
            data={"missing_quantity": "0", "return_to": "sets"},
        )
        self.client.post(
            f"/sets/{first_set_id}/duplicate", data={"return_to": "sets"}
        )
        with legolist.database() as connection:
            second_set_id = connection.execute(
                "SELECT MAX(id) FROM sets"
            ).fetchone()[0]

        page = self.client.get("/sets").data
        self.assertIn(b"Confirmer le retrait", page)
        self.assertIn(b"data-confirm", page)
        self.assertNotIn(b"delete-button", page)
        self.assertNotIn(b"Je ne l'ai plus", page)
        response = self.client.post(f"/sets/{second_set_id}/sold")

        self.assertEqual(response.headers["Location"], "/sets")
        with legolist.database() as connection:
            states = connection.execute(
                "SELECT in_collection, in_gathering FROM sets ORDER BY id"
            ).fetchall()
            missing = connection.execute(
                "SELECT missing_quantity FROM set_parts WHERE set_id = ?",
                (second_set_id,),
            ).fetchone()[0]
        self.assertEqual([tuple(row) for row in states], [(1, 0), (0, 0)])
        self.assertEqual(missing, 3)
        self.assertEqual(
            self.client.get("/sets").data.count(b'class="set-card collection-set-card"'),
            1,
        )

    def test_collection_sets_are_collapsible_and_missing_parts_use_step_buttons(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        page = self.client.get("/sets")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"<details class=\"set-card collection-set-card\"", page.data)
        self.assertIn(b"<summary class=\"collection-set-summary\"", page.data)
        summary_start = page.data.index(b'<summary class="collection-set-summary">')
        summary_end = page.data.index(b"</summary>", summary_start)
        controls_position = page.data.index(b'class="collection-set-controls"', summary_start)
        self.assertLess(controls_position, summary_end)
        self.assertIn(b"Rebrickable", page.data[summary_start:summary_end])
        self.assertIn(b'<svg viewBox="0 0 24 24"', page.data[summary_start:summary_end])
        self.assertIn(b'aria-label="Retirer', page.data[summary_start:summary_end])
        self.assertNotIn(b">\xe2\x88\x92</button>", page.data[summary_start:summary_end])
        self.assertNotIn(b"collection-set-actions", page.data)
        self.assertIn(b"set-status-form collection-part-controls", page.data)
        self.assertIn(b'class="collection-part-card', page.data)
        self.assertIn(b"collection-part-image", page.data)
        self.assertIn(b"Marquer une pi", page.data)
        self.assertNotIn(b'name="missing_quantity"', page.data)

        with legolist.database() as connection:
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (set_id,)
            ).fetchone()["id"]
        response = self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "sets", "change": "-1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["missing"], 2)

    def test_set_piece_can_be_marked_all_found_in_one_ajax_action(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        with legolist.database() as connection:
            part_id = connection.execute("SELECT id FROM set_parts").fetchone()["id"]

        response = self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "sets", "mark_complete": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["missing"], 0)
        self.assertEqual(response.get_json()["set_missing"], 0)
        page = self.client.get("/sets").get_data(as_text=True)
        self.assertIn("Tout trouvé", page)

    def test_existing_set_can_refresh_its_rebrickable_image(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        with patch.object(
            legolist,
            "fetch_set_info",
            return_value={"set_img_url": "https://example.test/10312-cover.jpg"},
        ):
            response = self.client.post(f"/sets/{set_id}/refresh-image")

        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            image_url = connection.execute(
                "SELECT set_image_url FROM sets WHERE id = ?", (set_id,)
            ).fetchone()["set_image_url"]
        self.assertEqual(image_url, "https://example.test/10312-cover.jpg")
        self.assertNotIn(
            b"R\xc3\xa9cup\xc3\xa9rer l'image Rebrickable",
            self.client.get("/sets").data,
        )

    def test_existing_set_can_refresh_its_rebrickable_year(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        with patch.object(legolist, "fetch_set_info", return_value={"year": 2021}):
            response = self.client.post(f"/sets/{set_id}/refresh-info")

        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            year = connection.execute(
                "SELECT year FROM sets WHERE id = ?", (set_id,)
            ).fetchone()["year"]
        self.assertEqual(year, 2021)

    def test_missing_page_uses_gather_cards_and_ajax_tracks_owned_missing_totals(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")

        page = self.client.get("/manquantes")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'class="parts-grid"', page.data)
        self.assertIn(b'class="piece-card"', page.data)
        self.assertIn(b"BrickLink XML", page.data)
        self.assertIn(b"BrickOwl CSV", page.data)
        self.assertNotIn(b'name="missing_quantity"', page.data)

        with legolist.database() as connection:
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (set_id,)
            ).fetchone()["id"]
        response = self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "missing", "change": "-1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["part_missing"], 2)
        self.assertEqual(response.get_json()["total_missing"], 2)
        self.assertIn(b"2", self.client.get("/manquantes").data)

    def test_existing_database_sets_migrate_as_not_owned(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        with patch.object(legolist, "DATABASE_PATH", legacy_path):
            with legolist.database() as connection:
                connection.execute(
                    """
                    CREATE TABLE sets (
                        id INTEGER PRIMARY KEY,
                        set_num TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO sets (set_num, title) VALUES ('10312-1', 'Jazz Club')"
                )
            legolist.initialize_database()
            with legolist.database() as connection:
                row = connection.execute(
                    "SELECT set_num, in_collection, in_gathering FROM sets"
                ).fetchone()
        self.assertEqual(
            (row["set_num"], row["in_collection"], row["in_gathering"]),
            ("10312-1", 0, 1),
        )

    def test_existing_owned_sets_do_not_migrate_into_gathering(self):
        legacy_path = Path(self.temp_dir.name) / "owned-legacy.db"
        with patch.object(legolist, "DATABASE_PATH", legacy_path):
            with legolist.database() as connection:
                connection.execute(
                    """
                    CREATE TABLE sets (
                        id INTEGER PRIMARY KEY,
                        set_num TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        in_collection INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE set_parts (
                        id INTEGER PRIMARY KEY,
                        set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
                        part_num TEXT NOT NULL,
                        part_name TEXT NOT NULL,
                        color_id INTEGER NOT NULL DEFAULT 0,
                        color_name TEXT NOT NULL DEFAULT 'Unknown',
                        quantity INTEGER NOT NULL CHECK(quantity > 0),
                        missing_quantity INTEGER NOT NULL CHECK(missing_quantity >= 0),
                        image_url TEXT NOT NULL DEFAULT '',
                        UNIQUE(set_id, part_num, color_id)
                    )
                    """
                )
                connection.executemany(
                    "INSERT INTO sets (set_num, title, in_collection) VALUES (?, ?, ?)",
                    [
                        ("10312-1", "Jazz Club", 1),
                        ("31145-1", "Dragon rouge", 0),
                    ],
                )
                connection.execute(
                    """
                    INSERT INTO set_parts (
                        set_id, part_num, part_name, quantity, missing_quantity
                    ) VALUES (1, '3001', 'Brique', 2, 1)
                    """
                )
            legolist.initialize_database()
            with legolist.database() as connection:
                rows = connection.execute(
                    "SELECT set_num, in_collection, in_gathering FROM sets ORDER BY set_num"
                ).fetchall()
                part = connection.execute(
                    "SELECT set_id, part_num, missing_quantity FROM set_parts"
                ).fetchone()
        self.assertEqual(
            [tuple(row) for row in rows],
            [("10312-1", 1, 0), ("31145-1", 0, 1)],
        )
        self.assertEqual(tuple(part), (1, "3001", 1))

    def test_import_uses_rebrickable_inventory(self):
        set_info = {
            "name": "Le jazz club",
            "set_img_url": "https://example.test/10312.jpg",
        }
        part = {
            "part": {"part_num": "3001", "name": "Brique", "part_img_url": ""},
            "color": {"id": 4, "name": "Rouge"},
            "quantity": 2,
        }
        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
                legolist,
                "fetch_set_inventory",
                return_value=(
                    set_info,
                    [
                        {
                            "part_num": "3001",
                            "part_name": "Brique",
                            "color_id": 4,
                            "color_name": "Rouge",
                            "quantity": 2,
                            "image_url": "",
                        }
                    ],
                ),
            ):
                response = self.client.post("/sets", data={"set_num": "10312"})
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT s.title, s.set_image_url, p.quantity, p.missing_quantity "
                "FROM sets s JOIN set_parts p ON p.set_id = s.id"
            ).fetchone()
        self.assertEqual(
            (row["title"], row["set_image_url"], row["quantity"], row["missing_quantity"]),
            ("Le jazz club", "https://example.test/10312.jpg", 2, 2),
        )
        with legolist.database() as connection:
            set_id = connection.execute("SELECT id FROM sets").fetchone()["id"]
        self.client.post(f"/sets/{set_id}/collect")
        self.assertIn(
            b'src="https://example.test/10312.jpg"',
            self.client.get("/sets").data,
        )

    def test_rebrickable_inventory_omits_spare_parts(self):
        inventory_page = {
            "results": [
                {
                    "part": {"part_num": "3001", "name": "Brique"},
                    "color": {"id": 4, "name": "Rouge"},
                    "quantity": 2,
                },
                {
                    "part": {"part_num": "3002", "name": "Brique de rechange"},
                    "color": {"id": 4, "name": "Rouge"},
                    "quantity": 1,
                    "is_spare": True,
                },
            ],
            "next": None,
        }
        with patch.object(legolist, "fetch_set_info", return_value={"name": "Set"}):
            with patch.object(legolist, "rebrickable_get", return_value=inventory_page):
                _, parts = legolist.fetch_set_inventory("10312")

        self.assertEqual([part["part_num"] for part in parts], ["3001"])


if __name__ == "__main__":
    unittest.main()
