"""Client Rebrickable.

Chaque test pilote l'app par son client de test, sur une base temporaire.
"""

from pathlib import Path
from unittest.mock import patch
from brickbuddy import images
from brickbuddy import rebrickable
from brickbuddy.flask_app import app
import app as legolist
from testbase import SuiteTests

class RebrickableTests(SuiteTests):
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
        with patch.object(images, "IMAGE_CACHE_PATH", Path(self.temp_dir.name) / "images"):
            with app.test_request_context("/"):
                image_route = images.local_image_url(source_url)
                self.assertEqual(images.local_image_url(source_url), image_route)
                app.process_response(app.response_class())
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
    rebrickable,
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
    rebrickable, "fetch_theme_name", return_value="Creator"
                ) as fetch_theme:
                    with patch.object(
    rebrickable, "fetch_minifig_parts_for_set", return_value=[]
                    ):
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

    def test_existing_set_can_refresh_its_rebrickable_image(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        with patch.object(
    rebrickable,
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
        with patch.object(rebrickable, "fetch_set_info", return_value={"year": 2021}):
            response = self.client.post(f"/sets/{set_id}/refresh-info")

        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            year = connection.execute(
                "SELECT year FROM sets WHERE id = ?", (set_id,)
            ).fetchone()["year"]
        self.assertEqual(year, 2021)

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
    rebrickable,
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
                with patch.object(
    rebrickable, "fetch_minifig_parts_for_set", return_value=[]
                ):
                    response = self.client.post(
                        "/sets",
                        data={"set_num": "10312"},
                    )
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
        with patch.object(rebrickable, "fetch_set_info", return_value={"name": "Set"}):
            with patch.object(rebrickable, "rebrickable_get", return_value=inventory_page):
                _, parts = rebrickable.fetch_set_inventory("10312")

        self.assertEqual([part["part_num"] for part in parts], ["3001"])

    def test_fetch_set_inventory_includes_minifigs_and_skips_spares(self):
        def fake_rebrickable_get(path):
            if "/minifigs/" in path:
                return {
                    "results": [
                        {
                            "set_num": "fig-000123",
                            "set_name": "Figurine Harry Potter",
                            "quantity": 1,
                            "set_img_url": "https://example.test/fig.jpg",
                        },
                        {
                            "set_num": "fig-000987",
                            "set_name": "Figurine inutile",
                            "quantity": 0,
                            "set_img_url": "",
                        },
                    ],
                    "next": None,
                }
            return {
                "results": [
                    {
                        "part": {
                            "part_num": "3001",
                            "name": "Brique 2 x 4",
                            "part_img_url": "https://example.test/3001.png",
                        },
                        "color": {"id": 4, "name": "Rouge"},
                        "quantity": 2,
                    },
                    {
                        "part": {"part_num": "3002", "name": "Pièce de rechange"},
                        "color": {"id": 4, "name": "Rouge"},
                        "quantity": 1,
                        "is_spare": True,
                    },
                ],
                "next": None,
            }

        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
    rebrickable, "rebrickable_get", side_effect=fake_rebrickable_get
            ):
                _, parts = rebrickable.fetch_set_inventory("10312-1")

        by_num = {part["part_num"]: part for part in parts}
        self.assertEqual(sorted(by_num), ["3001", "fig-000123"])
        minifig = by_num["fig-000123"]
        self.assertEqual(minifig["item_type"], "minifig")
        self.assertEqual(minifig["color_id"], 0)
        self.assertEqual(minifig["color_name"], "Figurine")
        self.assertEqual(minifig["part_name"], "Figurine Harry Potter")
        self.assertEqual(minifig["quantity"], 1)
        self.assertEqual(minifig["image_url"], "https://example.test/fig.jpg")
        self.assertEqual(by_num["3001"]["item_type"], "part")
        self.assertEqual(by_num["3001"]["quantity"], 2)

    def test_fetch_set_inventory_survives_minifig_failure(self):
        def fake_rebrickable_get(path):
            if "/minifigs/" in path:
                raise RuntimeError("API indisponible")
            return {
                "results": [
                    {
                        "part": {"part_num": "3001", "name": "Brique 2 x 4"},
                        "color": {"id": 4, "name": "Rouge"},
                        "quantity": 2,
                    }
                ],
                "next": None,
            }

        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
    rebrickable, "rebrickable_get", side_effect=fake_rebrickable_get
            ):
                _, parts = rebrickable.fetch_set_inventory("10312-1")

        self.assertEqual(
            [(part["part_num"], part["item_type"]) for part in parts],
            [("3001", "part")],
        )

    def test_fetch_minifig_parts_ignores_spares_and_aggregates(self):
        def fake_rebrickable_get(path):
            if "minifigs/fig-000123/parts/" in path:
                return {
                    "results": [
                        {
                            "part": {
                                "part_num": "3001",
                                "name": "Brique 2 x 4",
                                "part_img_url": "https://example.test/3001.png",
                            },
                            "color": {"id": 4, "name": "Rouge"},
                            "quantity": 2,
                            "is_spare": False,
                        },
                        {
                            "part": {
                                "part_num": "3001",
                                "name": "Brique 2 x 4",
                                "part_img_url": "https://example.test/3001.png",
                            },
                            "color": {"id": 4, "name": "Rouge"},
                            "quantity": 1,
                            "is_spare": True,
                        },
                    ],
                    "next": None,
                }
            if "minifigs/fig-000456/parts/" in path:
                return {
                    "results": [
                        {
                            "part": {
                                "part_num": "3004",
                                "name": "Plaque 1 x 2",
                                "part_img_url": "",
                            },
                            "color": {"id": 0, "name": "Black"},
                            "quantity": 1,
                        }
                    ],
                    "next": None,
                }
            return {
                "results": [
                    {"set_num": "fig-000123", "quantity": 2},
                    {"set_num": "fig-000456", "quantity": 1},
                    {"set_num": "10312-1", "quantity": 1},
                ],
                "next": None,
            }

        with patch.object(rebrickable, "rebrickable_get", side_effect=fake_rebrickable_get):
            rows = rebrickable.fetch_minifig_parts_for_set("10312-1")

        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(
                set(row),
                {
                    "fig_num",
                    "part_num",
                    "part_name",
                    "color_id",
                    "color_name",
                    "quantity",
                    "image_url",
                },
            )
        by_key = {(row["fig_num"], row["part_num"]): row for row in rows}
        self.assertEqual(
            (by_key[("fig-000123", "3001")]["quantity"], by_key[("fig-000123", "3001")]["color_id"]),
            (3, 4),
        )
        self.assertEqual(
            by_key[("fig-000456", "3004")]["color_id"],
            0,
        )
        self.assertEqual(by_key[("fig-000456", "3004")]["color_name"], "Black")
        self.assertNotIn(("10312-1", "3001"), by_key)
        self.assertTrue(all(row["fig_num"].startswith("fig-") for row in rows))

    def test_fetch_minifig_parts_survives_minifig_failure(self):
        def fake_rebrickable_get(path):
            if "minifigs/fig-000123/parts/" in path:
                raise RuntimeError("boom")
            if "minifigs/fig-000456/parts/" in path:
                return {
                    "results": [
                        {
                            "part": {
                                "part_num": "3004",
                                "name": "Plaque 1 x 2",
                                "part_img_url": "",
                            },
                            "color": {"id": 0, "name": "Black"},
                            "quantity": 1,
                        }
                    ],
                    "next": None,
                }
            return {
                "results": [
                    {"set_num": "fig-000123", "quantity": 1},
                    {"set_num": "fig-000456", "quantity": 1},
                ],
                "next": None,
            }

        with patch.object(rebrickable, "rebrickable_get", side_effect=fake_rebrickable_get):
            rows = rebrickable.fetch_minifig_parts_for_set("10312-1")

        self.assertEqual(
            [(row["fig_num"], row["part_num"], row["quantity"]) for row in rows],
            [("fig-000456", "3004", 1)],
        )

        def failing_list(path):
            raise RuntimeError("liste indisponible")

        with patch.object(rebrickable, "rebrickable_get", side_effect=failing_list):
            with self.assertRaises(RuntimeError):
                rebrickable.fetch_minifig_parts_for_set("10312-1")
