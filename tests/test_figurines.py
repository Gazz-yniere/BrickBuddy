"""Figurines et leurs composants.

Chaque test pilote l'app par son client de test, sur une base temporaire.
"""

from unittest.mock import patch
import csv
import io
import xml.etree.ElementTree as ET
from brickbuddy import inventory
from brickbuddy import rebrickable
import app as legolist
from testbase import SuiteTests

class FigurinesTests(SuiteTests):
    def test_minifig_parts_can_be_marked_found_and_remain_found_after_refresh(self):
        response = self.client.post(
            "/sets",
            data={"set_num": "10312", "title": "Le jazz club"},
        )
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            set_id = connection.execute("SELECT id FROM sets").fetchone()["id"]
            connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name,
                     quantity, missing_quantity, item_type)
                VALUES (?, 'fig-000123', 'Figurine test', 0, 'Figurine', 1, 1, 'minifig')
                """,
                (set_id,),
            )
            inventory.replace_set_minifig_parts(
                connection,
                set_id,
                [
                    {
                        "fig_num": "fig-000123",
                        "part_num": "3001",
                        "part_name": "Brique 2 x 4",
                        "color_id": 4,
                        "color_name": "Rouge",
                        "quantity": 1,
                    }
                ],
            )
            part_id = connection.execute(
                "SELECT id FROM minifig_parts WHERE set_id = ?", (set_id,)
            ).fetchone()["id"]

        page = self.client.get("/pieces")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'class="minifig-part-status-form', page.data)
        self.assertIn(b'name="mark_complete" value="1"', page.data)
        response = self.client.post(
            f"/minifig-parts/{part_id}/status",
            data={"status": "found"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["missing_quantity"], 0)
        self.assertEqual(response.get_json()["missing"], 0)
        self.assertEqual(response.get_json()["set_missing"], 0)
        self.assertFalse(response.get_json()["gathering_complete"])

        with legolist.database() as connection:
            inventory.replace_set_minifig_parts(
                connection,
                set_id,
                [
                    {
                        "fig_num": "fig-000123",
                        "part_num": "3001",
                        "part_name": "Brique 2 x 4",
                        "color_id": 4,
                        "color_name": "Rouge",
                        "quantity": 2,
                    }
                ],
            )
            part = connection.execute(
                "SELECT id, quantity, missing_quantity FROM minifig_parts WHERE set_id = ?",
                (set_id,),
            ).fetchone()
            part_id = part["id"]
        self.assertEqual((part["quantity"], part["missing_quantity"]), (2, 1))

        response = self.client.post(
            f"/minifig-parts/{part_id}/status",
            data={"status": "missing"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["missing_quantity"], 2)

    def test_completing_minifig_component_stops_completed_collected_gathering(self):
        self.client.post("/sets", data={"set_num": "10312"})
        with legolist.database() as connection:
            set_id = connection.execute("SELECT id FROM sets").fetchone()["id"]
            connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name,
                     quantity, missing_quantity, item_type)
                VALUES (?, 'fig-001', 'Personnage', 0, 'Figurine', 1, 1, 'minifig')
                """,
                (set_id,),
            )
            inventory.replace_set_minifig_parts(
                connection, set_id,
                [{"fig_num": "fig-001", "part_num": "head", "part_name": "Tête",
                  "color_id": 1, "color_name": "Jaune", "quantity": 1}],
            )
            component_id = connection.execute(
                "SELECT id FROM minifig_parts WHERE set_id = ?", (set_id,)
            ).fetchone()["id"]
        self.client.post(f"/sets/{set_id}/collect")

        response = self.client.post(
            f"/minifig-parts/{component_id}/status",
            data={"mark_complete": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["gathering_complete"])
        self.assertEqual(response.get_json()["part_missing"], 0)
        self.assertEqual(response.get_json()["set_missing"], 0)

    def test_complete_set_parts_updates_minifig_parts(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO minifig_parts
                    (set_id, fig_num, part_num, part_name, color_id, color_name,
                     quantity, missing_quantity)
                VALUES (?, 'fig-000123', '3001', 'Brique', 4, 'Rouge', 2, 2)
                """,
                (set_id,),
            )

        self.client.post(f"/sets/{set_id}/complete-parts")
        with legolist.database() as connection:
            missing_quantity = connection.execute(
                "SELECT missing_quantity FROM minifig_parts WHERE set_id = ?",
                (set_id,),
            ).fetchone()["missing_quantity"]
        self.assertEqual(missing_quantity, 0)

        self.client.post(f"/sets/{set_id}/complete-parts")
        with legolist.database() as connection:
            missing_quantity = connection.execute(
                "SELECT missing_quantity FROM minifig_parts WHERE set_id = ?",
                (set_id,),
            ).fetchone()["missing_quantity"]
        self.assertEqual(missing_quantity, 2)

    def test_minifig_and_components_track_quantities_together(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name,
                     quantity, missing_quantity, item_type)
                VALUES (?, 'fig-001', 'Personnage', 0, 'Figurine', 2, 2, 'minifig')
                """,
                (set_id,),
            )
            fig_id = cursor.lastrowid
            inventory.replace_set_minifig_parts(
                connection, set_id,
                [
                    {"fig_num": "fig-001", "part_num": "head", "part_name": "Tête",
                     "color_id": 1, "color_name": "Jaune", "quantity": 1},
                    {"fig_num": "fig-001", "part_num": "hand", "part_name": "Main",
                     "color_id": 1, "color_name": "Jaune", "quantity": 2},
                ],
            )
            components = {
                row["part_num"]: row["id"]
                for row in connection.execute(
                    "SELECT id, part_num FROM minifig_parts WHERE set_id = ?", (set_id,)
                )
            }

        headers = {"X-Requested-With": "XMLHttpRequest"}
        response = self.client.post(
            f"/minifig-parts/{components['head']}/status",
            data={"change": "-1"}, headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["parent_id"], fig_id)
        self.assertEqual(response.get_json()["missing"], 2)
        self.assertEqual(response.get_json()["parent_quantity"], 2)
        self.assertEqual(response.get_json()["missing_quantity"], 1)
        self.assertFalse(response.get_json()["gathering_complete"])
        self.client.post(
            f"/minifig-parts/{components['hand']}/status",
            data={"change": "-1"}, headers=headers,
        )
        self.client.post(
            f"/minifig-parts/{components['hand']}/status",
            data={"change": "-1"}, headers=headers,
        )
        with legolist.database() as connection:
            missing = connection.execute(
                "SELECT missing_quantity FROM set_parts WHERE id = ?", (fig_id,)
            ).fetchone()[0]
            component_missing = {
                row["part_num"]: row["missing_quantity"]
                for row in connection.execute(
                    "SELECT part_num, missing_quantity FROM minifig_parts WHERE set_id = ?",
                    (set_id,),
                )
            }
        self.assertEqual(missing, 1)
        self.assertEqual(component_missing, {"head": 1, "hand": 2})

        response = self.client.post(
            f"/parts/{fig_id}/missing", data={"mark_complete": "1"}, headers=headers
        )
        self.assertEqual(
            {item["id"]: item["missing_quantity"] for item in response.get_json()["components"]},
            {components["head"]: 0, components["hand"]: 0},
        )
        with legolist.database() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT SUM(missing_quantity) FROM minifig_parts WHERE set_id = ?",
                    (set_id,),
                ).fetchone()[0],
                0,
            )
        self.client.post(
            f"/minifig-parts/{components['head']}/status",
            data={"change": "1"}, headers=headers,
        )
        with legolist.database() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT missing_quantity FROM set_parts WHERE id = ?", (fig_id,)
                ).fetchone()[0],
                1,
            )
        self.client.post(
            f"/parts/{fig_id}/missing", data={"change": "1"}, headers=headers
        )
        with legolist.database() as connection:
            component_missing = {
                row["part_num"]: row["missing_quantity"]
                for row in connection.execute(
                    "SELECT part_num, missing_quantity FROM minifig_parts WHERE set_id = ?",
                    (set_id,),
                )
            }
        self.assertEqual(component_missing, {"head": 2, "hand": 2})

    def test_existing_minifig_tracking_is_migrated_once(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name,
                     quantity, missing_quantity, item_type)
                VALUES (?, 'fig-001', 'Personnage', 0, 'Figurine', 3, 2, 'minifig')
                """,
                (set_id,),
            )
            connection.execute(
                """
                INSERT INTO minifig_parts
                    (set_id, fig_num, part_num, part_name, color_id, color_name,
                     quantity, missing_quantity, tracking_version)
                VALUES (?, 'fig-001', 'hand', 'Main', 1, 'Jaune', 2, 2, 0)
                """,
                (set_id,),
            )
        legolist.initialize_database()
        legolist.initialize_database()
        with legolist.database() as connection:
            component = connection.execute(
                "SELECT missing_quantity, tracking_version FROM minifig_parts WHERE set_id = ?",
                (set_id,),
            ).fetchone()
            parent = connection.execute(
                "SELECT missing_quantity FROM set_parts WHERE set_id = ? AND part_num = 'fig-001'",
                (set_id,),
            ).fetchone()
        self.assertEqual((component["missing_quantity"], component["tracking_version"]), (4, 1))
        self.assertEqual(parent["missing_quantity"], 2)

    def test_shared_minifig_component_updates_only_its_set(self):
        first_set = self.add_set_and_part()
        self.client.post("/sets", data={"set_num": "31145"})
        with legolist.database() as connection:
            second_set = connection.execute(
                "SELECT id FROM sets WHERE id != ?", (first_set,)
            ).fetchone()[0]
            component_ids = []
            for set_id in (first_set, second_set):
                connection.execute(
                    """
                    INSERT INTO set_parts
                        (set_id, part_num, part_name, color_id, color_name,
                         quantity, missing_quantity, item_type)
                    VALUES (?, 'fig-001', 'Personnage', 0, 'Figurine', 1, 1, 'minifig')
                    """,
                    (set_id,),
                )
                inventory.replace_set_minifig_parts(
                    connection, set_id,
                    [{"fig_num": "fig-001", "part_num": "head", "part_name": "Tête",
                      "color_id": 1, "color_name": "Jaune", "quantity": 1}],
                )
                component_ids.append(
                    connection.execute(
                        "SELECT id FROM minifig_parts WHERE set_id = ?", (set_id,)
                    ).fetchone()[0]
                )
        self.client.post(
            f"/minifig-parts/{component_ids[0]}/status",
            data={"mark_complete": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        with legolist.database() as connection:
            parents = connection.execute(
                """
                SELECT set_id, missing_quantity FROM set_parts
                WHERE part_num = 'fig-001' ORDER BY set_id
                """
            ).fetchall()
        self.assertEqual(
            [(row["set_id"], row["missing_quantity"]) for row in parents],
            [(first_set, 0), (second_set, 1)],
        )

    def test_exports_exclude_minifigs(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity, image_url, item_type)
                VALUES (?, 'fig-000123', 'Figurine Harry Potter', 0, 'Figurine', 1, 1, '', 'minifig')
                """,
                (set_id,),
            )
        bricklink = ET.fromstring(self.client.get("/export/bricklink.xml").data)
        item_ids = [item.find("ITEMID").text for item in bricklink.findall("ITEM")]
        self.assertEqual(item_ids, ["3001"])
        brickowl_rows = list(
            csv.reader(io.StringIO(self.client.get("/export/brickowl.csv").data.decode("utf-8")))
        )
        self.assertEqual(brickowl_rows, [["ItemNo", "Color", "Qty"], ["3001", "4", "3"]])

    def test_pieces_page_displays_minifig(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity, image_url, item_type)
                VALUES (?, 'fig-000123', 'Figurine Harry Potter', 0, 'Figurine', 1, 1, '', 'minifig')
                """,
                (set_id,),
            )
        page = self.client.get("/pieces")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Figurine Harry Potter", page.data)
        self.assertIn(b"swatch-figurine", page.data)

    def test_minifig_component_swatch_follows_its_color(self):
        # Un composant coloré porte l'hex de sa couleur ; une figurine, dont la
        # couleur n'a pas d'hex, garde la pastille dorée sans teinte.
        self.client.post("/sets", data={"set_num": "10312", "title": "Le jazz club"})
        with legolist.database() as connection:
            set_id = connection.execute("SELECT id FROM sets").fetchone()["id"]
            connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name,
                     quantity, missing_quantity, item_type)
                VALUES (?, 'fig-000123', 'Figurine test', 0, 'Figurine', 1, 1, 'minifig')
                """,
                (set_id,),
            )
            inventory.replace_set_minifig_parts(
                connection,
                set_id,
                [
                    {
                        "fig_num": "fig-000123",
                        "part_num": "3001",
                        "part_name": "Brique 2 x 4",
                        "color_id": 1,
                        "color_name": "Blue",
                        "quantity": 1,
                    }
                ],
            )

        page = self.client.get("/pieces").get_data(as_text=True)
        self.assertIn('<span class="minifig-part-meta" title="Blue" style="--brick: #0055BF"', page)
        # La figurine elle-meme : couleur sans hex, pastille doree, aucune teinte.
        self.assertIn('<summary class="color-header">', page)
        self.assertIn('class="color-swatch swatch-figurine"', page)

    def test_add_set_persists_minifig_parts(self):
        imported_parts = [
            {
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": 4,
                "color_name": "Rouge",
                "quantity": 3,
                "image_url": "",
            }
        ]
        minifig_rows = [
            {
                "fig_num": "fig-000123",
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": 4,
                "color_name": "Rouge",
                "quantity": 2,
                "image_url": "https://example.test/3001.png",
            }
        ]
        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
    rebrickable,
    "fetch_set_inventory",
                return_value=({"name": "Set importé", "theme_id": None, "set_img_url": "", "year": 2020}, imported_parts),
            ):
                with patch.object(
    rebrickable,
    "fetch_minifig_parts_for_set",
                    return_value=minifig_rows,
                ):
                    response = self.client.post(
                        "/sets",
                        data={"set_num": "10312", "return_to": "pieces"},
                    )

        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            set_id = connection.execute("SELECT id FROM sets").fetchone()["id"]
            minifig_rows_saved = connection.execute(
                """
                SELECT set_id, fig_num, part_num, quantity, image_url
                FROM minifig_parts
                """
            ).fetchall()
            fig_part_count = connection.execute(
                "SELECT COUNT(*) AS count FROM set_parts WHERE part_num LIKE 'fig-%'"
            ).fetchone()["count"]
        self.assertEqual(
            [(row["set_id"], row["fig_num"], row["part_num"], row["quantity"], row["image_url"]) for row in minifig_rows_saved],
            [(set_id, "fig-000123", "3001", 2, "https://example.test/3001.png")],
        )
        self.assertEqual(fig_part_count, 0)

    def test_minifig_parts_fetch_failure_does_not_block_add_set(self):
        imported_parts = [
            {
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
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
                return_value=({"name": "Set importé", "theme_id": None, "set_img_url": "", "year": 2020}, imported_parts),
            ):
                with patch.object(
    rebrickable,
    "fetch_minifig_parts_for_set",
                    side_effect=RuntimeError("api down"),
                ):
                    response = self.client.post(
                        "/sets",
                        data={"set_num": "10312", "return_to": "pieces"},
                    )

        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            set_count = connection.execute("SELECT COUNT(*) AS count FROM sets").fetchone()["count"]
            parts = connection.execute(
                "SELECT part_num, quantity FROM set_parts"
            ).fetchall()
            minifig_count = connection.execute(
                "SELECT COUNT(*) AS count FROM minifig_parts"
            ).fetchone()["count"]
        self.assertEqual(set_count, 1)
        self.assertEqual(
            [(row["part_num"], row["quantity"]) for row in parts],
            [("3001", 3)],
        )
        self.assertEqual(minifig_count, 0)

    def test_refresh_inventory_replaces_minifig_parts(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO minifig_parts
                    (set_id, fig_num, part_num, part_name, color_id, color_name, quantity, image_url)
                VALUES (?, 'fig-OLD', '3024', 'Ancienne brique', 4, 'Rouge', 1, '')
                """,
                (set_id,),
            )

        replacement_parts = [
            {
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": 4,
                "color_name": "Rouge",
                "quantity": 3,
                "image_url": "",
            }
        ]
        replacement_minifigs = [
            {
                "fig_num": "fig-NEW",
                "part_num": "3004",
                "part_name": "Plaque 1 x 2",
                "color_id": 0,
                "color_name": "Black",
                "quantity": 2,
                "image_url": "",
            }
        ]
        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
    rebrickable,
    "fetch_set_inventory",
                return_value=({"name": "Set de test"}, replacement_parts),
            ):
                with patch.object(
    rebrickable,
    "fetch_minifig_parts_for_set",
                    return_value=replacement_minifigs,
                ):
                    response = self.client.post(
                        f"/sets/{set_id}/refresh-inventory",
                        data={"return_to": "pieces"},
                    )

        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            rows = connection.execute(
                "SELECT fig_num, part_num, quantity FROM minifig_parts WHERE set_id = ?",
                (set_id,),
            ).fetchall()
        self.assertEqual(
            [(row["fig_num"], row["part_num"], row["quantity"]) for row in rows],
            [("fig-NEW", "3004", 2)],
        )

    def test_refresh_inventory_keeps_minifig_parts_when_fetch_fails(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO minifig_parts
                    (set_id, fig_num, part_num, part_name, color_id, color_name, quantity, image_url)
                VALUES (?, 'fig-000123', '3001', 'Brique 2 x 4', 4, 'Rouge', 2, '')
                """,
                (set_id,),
            )

        replacement_parts = [
            {
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": 4,
                "color_name": "Rouge",
                "quantity": 5,
                "image_url": "",
            }
        ]
        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
    rebrickable,
    "fetch_set_inventory",
                return_value=({"name": "Set de test"}, replacement_parts),
            ):
                with patch.object(
    rebrickable,
    "fetch_minifig_parts_for_set",
                    side_effect=RuntimeError("api down"),
                ):
                    response = self.client.post(
                        f"/sets/{set_id}/refresh-inventory",
                        data={"return_to": "pieces"},
                    )

        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            minifig_rows = connection.execute(
                "SELECT fig_num, part_num, quantity FROM minifig_parts WHERE set_id = ?",
                (set_id,),
            ).fetchall()
            part_rows = connection.execute(
                "SELECT part_num, quantity FROM set_parts WHERE set_id = ?",
                (set_id,),
            ).fetchall()
        self.assertEqual(
            [(row["fig_num"], row["part_num"], row["quantity"]) for row in minifig_rows],
            [("fig-000123", "3001", 2)],
        )
        self.assertEqual(
            [(row["part_num"], row["quantity"]) for row in part_rows],
            [("3001", 5)],
        )

    def test_duplicate_set_copies_minifig_parts(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO minifig_parts
                    (set_id, fig_num, part_num, part_name, color_id, color_name, quantity, image_url)
                VALUES (?, 'fig-000123', '3001', 'Brique 2 x 4', 4, 'Rouge', 2, '')
                """,
                (set_id,),
            )

        response = self.client.post(
            f"/sets/{set_id}/duplicate",
            data={"return_to": "pieces"},
        )
        self.assertEqual(response.status_code, 302)

        with legolist.database() as connection:
            set_ids = [row["id"] for row in connection.execute("SELECT id FROM sets ORDER BY id")]
            rows = connection.execute(
                """
                SELECT set_id, fig_num, part_num, quantity, missing_quantity
                FROM minifig_parts ORDER BY set_id
                """
            ).fetchall()

        self.assertEqual(len(set_ids), 2)
        self.assertEqual(
            [
                (
                    row["set_id"],
                    row["fig_num"],
                    row["part_num"],
                    row["quantity"],
                    row["missing_quantity"],
                )
                for row in rows
            ],
            [
                (set_id, "fig-000123", "3001", 2, 0),
                (set_ids[1], "fig-000123", "3001", 2, 2),
            ],
        )
        self.assertNotEqual(set_id, set_ids[1])

    def test_minifig_parts_render_on_pieces_page_and_stay_hidden_without_data(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity, image_url, item_type)
                VALUES (?, 'fig-000123', 'Figurine Harry Potter', 0, 'Figurine', 1, 1, '', 'minifig')
                """,
                (set_id,),
            )
            connection.execute(
                """
                INSERT INTO minifig_parts
                    (set_id, fig_num, part_num, part_name, color_id, color_name, quantity, image_url)
                VALUES (?, 'fig-000123', '3001', 'Brique', 4, 'Rouge', 2, '')
                """,
                (set_id,),
            )

        page = self.client.get("/pieces")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'class="minifig-parts"', page.data)
        self.assertIn(b"minifig-parts-label", page.data)
        self.assertIn(b">Brique<", page.data)
        self.assertIn(b">/2</span>", page.data)
        # La pièce normale (quantity 3) conserve son total : ×3.
        self.assertIn(b"\xc3\x973", page.data)

        with legolist.database() as connection:
            connection.execute("DELETE FROM minifig_parts WHERE set_id = ?", (set_id,))
        page = self.client.get("/pieces")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'class="minifig-parts"', page.data)
        self.assertNotIn(b"\xc3\x972", page.data)
        self.assertIn(b"\xc3\x973", page.data)

    def test_delete_set_removes_minifig_parts(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO minifig_parts
                    (set_id, fig_num, part_num, part_name, color_id, color_name, quantity, image_url)
                VALUES (?, 'fig-000123', '3001', 'Brique 2 x 4', 4, 'Rouge', 2, '')
                """,
                (set_id,),
            )

        response = self.client.post(f"/sets/{set_id}/delete")

        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            remaining_sets = connection.execute("SELECT COUNT(*) AS count FROM sets").fetchone()["count"]
            remaining_parts = connection.execute(
                "SELECT COUNT(*) AS count FROM minifig_parts"
            ).fetchone()["count"]
            remaining_set_parts = connection.execute(
                "SELECT COUNT(*) AS count FROM set_parts"
            ).fetchone()["count"]
        self.assertEqual(remaining_sets, 0)
        self.assertEqual(remaining_parts, 0)
        self.assertEqual(remaining_set_parts, 0)
