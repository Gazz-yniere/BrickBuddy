"""Inventaire, vrac et exports.

Chaque test pilote l'app par son client de test, sur une base temporaire.
"""

import re
from unittest.mock import patch
import xml.etree.ElementTree as ET
from brickbuddy import inventory
from brickbuddy import rebrickable
import app as legolist
from testbase import SuiteTests

class InventaireTests(SuiteTests):
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
        self.assertIn(b'class="color-header" style="--brick: #C91A09"', page.data)
        self.assertIn(b"Mon inventaire", page.data)
        self.assertIn(b"Red", page.data)
        self.assertIn(b"Brique 2 x 4", page.data)
        self.assertIn(b"R\xc3\xa9f. 3001", page.data)
        self.assertIn(b"\xc3\x974", page.data)
        self.assertNotIn(b'class="inventory-set', page.data)

        filtered_page = self.client.get("/inventaire?color=Rouge&q=3001")
        self.assertEqual(filtered_page.status_code, 200)
        self.assertIn(b"Brique 2 x 4", filtered_page.data)
        self.assertNotIn(b"Inventaire vide", filtered_page.data)

    def test_inventory_groups_a_color_once_whatever_its_spelling(self):
        # Une même couleur enregistrée sous deux graphies doit faire une seule carte.
        self.add_stock_part("3001", color_id=4, color_name="Red")
        self.add_stock_part("3002", color_id=4, color_name="Rouge")
        self.add_stock_part("3003", color_id=1, color_name="bleu")
        page = self.client.get("/inventaire").get_data(as_text=True)

        labels = re.findall(r'<div class="color-heading"><h3>([^<]+)</h3>', page)
        self.assertEqual(labels, ["Blue", "Red"])
        self.assertEqual(page.count('class="color-card inventory-color"'), 2)
        # La pastille et l'entete prennent l'hex de la couleur officielle.
        self.assertEqual(
            re.findall(r'<summary class="color-header" style="--brick: (#[0-9A-F]{6})"', page),
            ["#0055BF", "#C91A09"],
        )

        # Le filtre accepte n'importe quelle graphie de la même couleur.
        for spelling in ("Rouge", "Red", "rouge"):
            filtered = self.client.get(f"/inventaire?color={spelling}").get_data(as_text=True)
            self.assertEqual(filtered.count('class="color-card inventory-color"'), 1)
            self.assertIn("Réf. 3001", filtered)
            self.assertIn("Réf. 3002", filtered)
            self.assertNotIn("Réf. 3003", filtered)

        # Le menu des couleurs ne propose qu'une ligne par couleur : le texte est le nom
        # officiel en anglais, la valeur envoyée au serveur est ce même nom.
        options = re.findall(
            r'<option value="(\d+)" data-name="([^"]+)">([^<]+)</option>', page
        )
        self.assertEqual([(name, label) for _, name, label in options], [("Blue", "Blue"), ("Red", "Red")])
        self.assertEqual(page.count('<option value="Red"'), 1)
        self.assertEqual(page.count('<option value="Blue"'), 1)

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
            owned = connection.execute(
                """
                SELECT p.quantity - p.missing_quantity AS owned
                FROM set_parts p JOIN sets s ON s.id = p.set_id
                """
            ).fetchall()
            orphans = connection.execute(
                "SELECT COUNT(*) FROM set_parts WHERE set_id NOT IN (SELECT id FROM sets)"
            ).fetchone()[0]
        # L'exemplaire vendu ne laisse aucune ligne invisible ni pièce orpheline.
        self.assertEqual([tuple(row) for row in states], [(1, 0)])
        self.assertEqual([row["owned"] for row in owned], [3])
        self.assertEqual(orphans, 0)
        self.assertEqual(
            self.client.get("/sets").data.count(b'class="set-card collection-set-card"'),
            1,
        )
        self.assertIn('data-total="3"', self.client.get("/inventaire").get_data(as_text=True))

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

    def test_refresh_inventory_replaces_parts_and_preserves_missing(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity, image_url)
                VALUES (?, '3004sp', 'Pièce de rechange', 4, 'Rouge', 1, 1, '')
                """,
                (set_id,),
            )
            connection.execute(
                "UPDATE set_parts SET missing_quantity = 2 WHERE set_id = ? AND part_num = '3001'",
                (set_id,),
            )

        def fake_rebrickable_get(path):
            if "/minifigs/" in path:
                return {
                    "results": [
                        {
                            "set_num": "fig-000123",
                            "set_name": "Figurine Harry Potter",
                            "quantity": 1,
                            "set_img_url": "https://example.test/fig.jpg",
                        }
                    ],
                    "next": None,
                }
            return {
                "results": [
                    {
                        "part": {"part_num": "3001", "name": "Brique 2 x 4"},
                        "color": {"id": 4, "name": "Rouge"},
                        "quantity": 3,
                    },
                    {
                        "part": {"part_num": "3002", "name": "Brique 1 x 3"},
                        "color": {"id": 4, "name": "Rouge"},
                        "quantity": 1,
                    },
                ],
                "next": None,
            }

        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
    rebrickable, "rebrickable_get", side_effect=fake_rebrickable_get
            ):
                response = self.client.post(
                    f"/sets/{set_id}/refresh-inventory",
                    data={"return_to": "pieces"},
                )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/pieces", response.location)
        with legolist.database() as connection:
            rows = connection.execute(
                """
                SELECT part_num, item_type, quantity, missing_quantity
                FROM set_parts WHERE set_id = ? ORDER BY part_num
                """,
                (set_id,),
            ).fetchall()
        self.assertEqual(
            [
                (
                    row["part_num"],
                    row["item_type"],
                    row["quantity"],
                    row["missing_quantity"],
                )
                for row in rows
            ],
            [
                ("3001", "part", 3, 2),
                ("3002", "part", 1, 1),
                ("fig-000123", "minifig", 1, 1),
            ],
        )
        # 3001 : missing préservé (min(2, 3)) ; 3002 : borné à la quantité (min(9, 1)) ;
        # la pièce de rechange 3004sp a disparu ; la figurine arrive avec missing = quantity.
        with legolist.database() as connection:
            connection.execute(
                "UPDATE set_parts SET missing_quantity = 9 WHERE set_id = ? AND part_num = '3002'",
                (set_id,),
            )
        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
    rebrickable, "rebrickable_get", side_effect=fake_rebrickable_get
            ):
                self.client.post(f"/sets/{set_id}/refresh-inventory")
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT missing_quantity FROM set_parts WHERE set_id = ? AND part_num = '3002'",
                (set_id,),
            ).fetchone()
        self.assertEqual(row["missing_quantity"], 1)

    def test_refresh_inventory_with_empty_import_keeps_existing_parts(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                "UPDATE set_parts SET missing_quantity = 2 WHERE set_id = ? AND part_num = '3001'",
                (set_id,),
            )

        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "test-key"}):
            with patch.object(
    rebrickable,
    "fetch_set_inventory",
                return_value=({"name": "Set de test"}, []),
            ):
                with patch.object(
    rebrickable, "fetch_minifig_parts_for_set", return_value=[]
                ):
                    response = self.client.post(f"/sets/{set_id}/refresh-inventory")

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as browser_session:
            flashes = [message for _, message in browser_session.get("_flashes", [])]
        self.assertIn(
            "Inventaire introuvable : aucune pièce n'a été renvoyée par Rebrickable.",
            flashes,
        )
        with legolist.database() as connection:
            rows = connection.execute(
                """
                SELECT part_num, quantity, missing_quantity
                FROM set_parts WHERE set_id = ?
                """,
                (set_id,),
            ).fetchall()
        self.assertEqual(
            [(row["part_num"], row["quantity"], row["missing_quantity"]) for row in rows],
            [("3001", 3, 2)],
        )

    def test_stock_parts_can_be_added_incremented_and_deleted(self):
        row = self.add_stock_part("3001", color_id=4, quantity=5, part_name="Brique 2 x 4")
        self.assertEqual(row["quantity"], 5)

        # Un nouvel ajout de la même référence/couleur incrémente la quantité.
        response = self.client.post(
            "/stock",
            data={
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": "4",
                "color_name": "Rouge",
                "quantity": "3",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("3 × Brique 2 x 4 ajouté(s) au vrac.".encode("utf-8"), response.data)
        with legolist.database() as connection:
            stored = connection.execute(
                "SELECT quantity FROM stock_parts WHERE id = ?", (row["id"],)
            ).fetchone()
        self.assertEqual(stored["quantity"], 8)

        # Ajustement relatif.
        response = self.client.post(
            f"/stock/{row['id']}/adjust",
            data={"change": "-2"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Brique 2 x 4 : 6 dans le vrac.".encode("utf-8"), response.data)
        with legolist.database() as connection:
            stored = connection.execute(
                "SELECT quantity FROM stock_parts WHERE id = ?", (row["id"],)
            ).fetchone()
        self.assertEqual(stored["quantity"], 6)

        # Ajustement absolu.
        response = self.client.post(
            f"/stock/{row['id']}/adjust",
            data={"quantity": "1"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Brique 2 x 4 : 1 dans le vrac.".encode("utf-8"), response.data)

        # Une quantité ramenée à zéro supprime l'entrée du vrac.
        response = self.client.post(
            f"/stock/{row['id']}/adjust",
            data={"change": "-1"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Brique 2 x 4 retiré du vrac.".encode("utf-8"), response.data)
        with legolist.database() as connection:
            gone = connection.execute(
                "SELECT id FROM stock_parts WHERE id = ?", (row["id"],)
            ).fetchone()
        self.assertIsNone(gone)

        # Suppression explicite via la route dédiée.
        row = self.add_stock_part("3001", color_id=4, quantity=2, part_name="Brique 2 x 4")
        response = self.client.post(
            f"/stock/{row['id']}/delete",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Brique 2 x 4 retiré du vrac.".encode("utf-8"), response.data)
        with legolist.database() as connection:
            gone = connection.execute(
                "SELECT id FROM stock_parts WHERE id = ?", (row["id"],)
            ).fetchone()
        self.assertIsNone(gone)

    def test_inventory_separates_stock_sets_and_reserved(self):
        self.add_stock_part("3001", color_id=4, quantity=3)
        collected_id = self.create_collected_set("75192")
        self.insert_set_part(
            collected_id, "3001", color_id=4, quantity=4, missing_quantity=2
        )
        gathering_id = self.create_gathering_set("31145")
        self.insert_set_part(
            gathering_id, "3001", color_id=4, quantity=5, missing_quantity=3
        )

        with legolist.database() as connection:
            owned = inventory.get_owned_parts(connection)
        part = owned[("3001", 4)]
        self.assertEqual(part["stock_qty"], 3)
        self.assertEqual(part["set_qty"], 2)
        self.assertEqual(part["reserved_qty"], 2)
        self.assertEqual(part["total"], 7)
        self.assertEqual(part["origin"], "mixed")

        page = self.client.get("/inventaire")
        self.assertEqual(page.status_code, 200)
        self.assertIn(
            b'data-part="3001" data-color="4" data-total="7" data-stock="3" '
            b'data-sets="2" data-reserved="2" data-origin="mixed"',
            page.data,
        )
        # Les badges ont disparu au profit des lignes d'allocation.
        self.assertNotIn(b"part-badge", page.data)
        self.assertIn(b'class="alloc-row alloc-sets"', page.data)
        self.assertIn(b'class="alloc-row alloc-reserved"', page.data)

        self.add_stock_part("3002", color_id=4, quantity=1)
        self.insert_set_part(collected_id, "3003", color_id=4, quantity=2, missing_quantity=0)
        self.insert_set_part(gathering_id, "3004", color_id=4, quantity=2, missing_quantity=1)
        page = self.client.get("/inventaire")
        self.assertIn(b'class="stock-stepper"', page.data)
        self.assertIn('aria-label="3 pièces en vrac"'.encode(), page.data)
        self.assertIn('aria-label="0 pièces en vrac"'.encode(), page.data)
        self.assertIn(b'class="stock-buttons"', page.data)
        self.assertNotIn(b'class="stock-delete-form"', page.data)
        self.assertIn(b'data-part="3004" data-color="4" data-total="1"', page.data)
        self.assertNotIn(b"part-badge", page.data)

    def test_inventory_stock_stepper_handles_zero_and_other_origins(self):
        collected_id = self.create_collected_set("75192")
        self.insert_set_part(
            collected_id, "3001", color_id=4, quantity=2, missing_quantity=0
        )
        stock = self.add_stock_part("3001", color_id=4, quantity=1)
        headers = {"X-Requested-With": "XMLHttpRequest"}
        response = self.client.post(
            f"/stock/{stock['id']}/adjust", data={"change": "-1"}, headers=headers
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertFalse(result["removed"])
        self.assertIn('aria-label="0 pièces en vrac"', result["html"])
        self.assertNotIn('class="stock-delete', result["html"])
        self.assertIn('class="stock-add-form"', result["html"])

        response = self.client.post(
            "/stock",
            data={"part_num": "3001", "part_name": "Pièce 3001", "color_id": "4",
                  "color_name": "Rouge", "quantity": "1"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('aria-label="1 pièce en vrac"', response.get_json()["html"])

        only_stock = self.add_stock_part("3002", color_id=4, quantity=1)
        response = self.client.post(
            f"/stock/{only_stock['id']}/adjust",
            data={"change": "-1"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["removed"])

    def test_pieces_page_offers_stock_for_missing_part(self):
        self.add_stock_part("3001", color_id=4, quantity=3)
        gathering_id = self.create_gathering_set("75192")
        self.insert_set_part(gathering_id, "3001", color_id=4, quantity=2, missing_quantity=2)
        page = self.client.get("/pieces")
        self.assertIn(b"Prendre dans le vrac", page.data)
        self.assertIn("suffisant".encode(), page.data)

        result = self.client.post(
            "/pieces/take-stock",
            data={"part_num": "3001", "color_id": "4"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["taken"], 2)
        self.assertEqual(result.get_json()["stock_qty"], 1)

    def test_inventory_origin_filter(self):
        self.add_stock_part("3001", color_id=4, quantity=3)
        collected_id = self.create_collected_set("75192")
        self.insert_set_part(collected_id, "3002", color_id=4, quantity=4, missing_quantity=2)
        gathering_id = self.create_gathering_set("31145")
        self.insert_set_part(gathering_id, "3003", color_id=4, quantity=5, missing_quantity=3)
        self.add_stock_part("3004", color_id=4, quantity=2)
        self.insert_set_part(collected_id, "3004", color_id=4, quantity=1, missing_quantity=0)

        page = self.client.get("/inventaire?origin=stock")
        self.assertIn(b'data-part="3001"', page.data)
        self.assertIn(b'data-part="3004"', page.data)
        self.assertNotIn(b'data-part="3002"', page.data)
        self.assertNotIn(b'data-part="3003"', page.data)

        page = self.client.get("/inventaire?origin=sets")
        self.assertIn(b'data-part="3002"', page.data)
        self.assertIn(b'data-part="3004"', page.data)
        self.assertNotIn(b'data-part="3001"', page.data)
        self.assertNotIn(b'data-part="3003"', page.data)

        page = self.client.get("/inventaire?origin=reserved")
        self.assertIn(b'data-part="3003"', page.data)
        self.assertNotIn(b'data-part="3001"', page.data)
        self.assertNotIn(b'data-part="3002"', page.data)
        self.assertNotIn(b'data-part="3004"', page.data)

        page = self.client.get("/inventaire?origin=mixed")
        self.assertIn(b'data-part="3004"', page.data)
        self.assertNotIn(b'data-part="3001"', page.data)
        self.assertNotIn(b'data-part="3002"', page.data)
        self.assertNotIn(b'data-part="3003"', page.data)

        # Une origine inconnue retombe sur « tout ».
        page = self.client.get("/inventaire?origin=absurde")
        self.assertIn(b'data-part="3001"', page.data)
        self.assertIn(b'data-part="3002"', page.data)
        self.assertIn(b'data-part="3003"', page.data)
        self.assertIn(b'data-part="3004"', page.data)

    def test_take_stock_transfers_from_stock_without_changing_total(self):
        set_id = self.create_gathering_set("31145")
        self.insert_set_part(
            set_id, "3001", color_id=4, quantity=5, missing_quantity=5
        )
        self.add_stock_part("3001", color_id=4, quantity=5)

        # Prise complète : le vrac est vidé et le total possédé ne change pas.
        response = self.client.post(
            f"/sets/{set_id}/take-stock", follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("5 pièces prises dans le vrac.".encode("utf-8"), response.data)
        with legolist.database() as connection:
            stock_row = connection.execute(
                "SELECT quantity FROM stock_parts WHERE part_num = '3001'"
            ).fetchone()
            part_row = connection.execute(
                """
                SELECT missing_quantity FROM set_parts
                WHERE set_id = ? AND part_num = '3001'
                """,
                (set_id,),
            ).fetchone()
            owned = inventory.get_owned_parts(connection)
        self.assertIsNone(stock_row)
        self.assertEqual(part_row["missing_quantity"], 0)
        part = owned[("3001", 4)]
        self.assertEqual(part["total"], 5)
        self.assertEqual(part["stock_qty"], 0)
        self.assertEqual(part["reserved_qty"], 5)

        # Prise partielle depuis la page des sets à réunir.
        self.add_stock_part("3001", color_id=4, quantity=5)
        with legolist.database() as connection:
            connection.execute(
                "UPDATE set_parts SET missing_quantity = 2 WHERE set_id = ?", (set_id,)
            )
        page = self.client.get("/pieces")
        self.assertNotIn("Prendre le vrac · 5".encode("utf-8"), page.data)
        self.assertIn(b'class="stock-take-form" action="/pieces/take-stock"', page.data)
        self.assertIn("Prendre dans le vrac".encode("utf-8"), page.data)
        response = self.client.post(
            f"/sets/{set_id}/take-stock", data={"return_to": "pieces"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/pieces", response.location)
        page = self.client.get("/pieces")
        self.assertIn("2 pièces prises dans le vrac.".encode("utf-8"), page.data)
        with legolist.database() as connection:
            stock_row = connection.execute(
                "SELECT quantity FROM stock_parts WHERE part_num = '3001'"
            ).fetchone()
            part_row = connection.execute(
                """
                SELECT missing_quantity FROM set_parts
                WHERE set_id = ? AND part_num = '3001'
                """,
                (set_id,),
            ).fetchone()
        self.assertEqual(stock_row["quantity"], 3)
        self.assertEqual(part_row["missing_quantity"], 0)

        # Prise unique avec retour vers la page de vérification.
        with legolist.database() as connection:
            connection.execute(
                "UPDATE set_parts SET missing_quantity = 1 WHERE set_id = ?", (set_id,)
            )
        response = self.client.post(
            f"/sets/{set_id}/take-stock", data={"return_to": "verify"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/inventaire/verifier?set_num=31145-1", response.location)
        page = self.client.get("/inventaire/verifier")
        self.assertIn("1 pièce prise dans le vrac.".encode("utf-8"), page.data)
        with legolist.database() as connection:
            stock_row = connection.execute(
                "SELECT quantity FROM stock_parts WHERE part_num = '3001'"
            ).fetchone()
        self.assertEqual(stock_row["quantity"], 2)

        # Aucune pièce du vrac correspondante : message d'erreur.
        with legolist.database() as connection:
            connection.execute("DELETE FROM stock_parts")
            connection.execute(
                "UPDATE set_parts SET missing_quantity = 1 WHERE set_id = ?", (set_id,)
            )
        response = self.client.post(
            f"/sets/{set_id}/take-stock", follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Aucune pièce du vrac ne correspond aux pièces manquantes de ce set.".encode(
                "utf-8"
            ),
            response.data,
        )

    def test_verify_set_page_without_api_key_shows_configuration_message(self):
        page = self.client.get("/inventaire/verifier")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"verify-result", page.data)
        self.assertNotIn(b"Configurez REBRICKABLE_API_KEY", page.data)

        page = self.client.get("/inventaire/verifier?set_num=31145")
        self.assertEqual(page.status_code, 200)
        self.assertIn(
            "Configurez REBRICKABLE_API_KEY pour vérifier un set.".encode("utf-8"),
            page.data,
        )
        self.assertIn(b'value="31145-1"', page.data)
        self.assertNotIn(b"verify-result", page.data)

        page = self.client.get("/inventaire/verifier?set_num=10312/2")
        self.assertEqual(page.status_code, 200)
        self.assertIn(
            "Numéro de set invalide : 10312/2.".encode("utf-8"), page.data
        )

    def test_verify_set_page_compares_needed_with_owned_parts(self):
        self.add_stock_part("3001", color_id=4, quantity=4)
        collected_id = self.create_collected_set("75192")
        self.insert_set_part(collected_id, "3001", color_id=4, quantity=2, missing_quantity=0)
        gathering_id = self.create_gathering_set("31145")

        set_info = {
            "name": "Set de test",
            "set_img_url": "",
            "year": 2024,
            "theme_id": None,
        }
        api_parts = [
            {
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": 4,
                "color_name": "Rouge",
                "quantity": 10,
                "image_url": "",
                "item_type": "part",
            },
            {
                "part_num": "3002",
                "part_name": "Plaque 2 x 2",
                "color_id": 11,
                "color_name": "Bleu",
                "quantity": 3,
                "image_url": "",
                "item_type": "part",
            },
        ]

        with patch.dict(
            "os.environ", {"REBRICKABLE_API_KEY": "test-key"}
        ), patch.object(
    rebrickable, "fetch_set_inventory", return_value=(set_info, api_parts)
        ) as fetch_mock:
            page = self.client.get("/inventaire/verifier?set_num=31145")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(fetch_mock.call_count, 1)
        self.assertEqual(fetch_mock.call_args[0][0], "31145-1")

        # 3001 : besoin 10, vrac 4, sets 2 → prendre 4, acheter 4.
        self.assertIn(
            b'data-part="3001" data-color="4" data-stock="4" data-sets="2" data-to-buy="4"',
            page.data,
        )
        # 3002 : besoin 3, rien en vrac ni en set → acheter 3.
        self.assertIn(
            b'data-part="3002" data-color="11" data-stock="0" data-sets="0" data-to-buy="3"',
            page.data,
        )
        # Résumé global.
        self.assertIn("<strong>13</strong><span>à réunir</span>".encode("utf-8"), page.data)
        self.assertIn(
            "<strong>4</strong><span>dispo en vrac</span>".encode("utf-8"), page.data
        )
        self.assertIn("<strong>2</strong><span>dans un set</span>".encode("utf-8"), page.data)
        self.assertIn("<strong>7</strong><span>à acheter</span>".encode("utf-8"), page.data)
        self.assertIn("Set de test".encode("utf-8"), page.data)
        # Le set existe déjà à réunir : le CTA propose de prendre le vrac.
        self.assertIn(b'name="return_to" value="verify"', page.data)
        self.assertIn(f"/sets/{gathering_id}/take-stock".encode("ascii"), page.data)

    def test_inventory_hides_parts_entirely_missing_from_collected_sets(self):
        collected_id = self.create_collected_set("75192")
        self.insert_set_part(
            collected_id, "3001", color_id=4, quantity=4, missing_quantity=4
        )
        self.insert_set_part(
            collected_id, "3002", color_id=4, quantity=4, missing_quantity=2
        )

        with legolist.database() as connection:
            owned = inventory.get_owned_parts(connection)
        # Une pièce absente d'un set possédé ne doit pas apparaître à « ×0 ».
        self.assertNotIn(("3001", 4), owned)
        self.assertEqual(owned[("3002", 4)]["total"], 2)

        page = self.client.get("/inventaire")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'data-part="3001"', page.data)
        self.assertIn(b'data-part="3002" data-color="4" data-total="2"', page.data)

    def test_verify_set_counts_reserved_parts_as_owned_in_sets(self):
        gathering_id = self.create_gathering_set("31145")
        self.insert_set_part(
            gathering_id, "3001", color_id=4, quantity=5, missing_quantity=3
        )

        set_info = {"name": "Set de test", "set_img_url": "", "year": 2024}
        api_parts = [
            {
                "part_num": "3001",
                "part_name": "Brique 2 x 4",
                "color_id": 4,
                "color_name": "Rouge",
                "quantity": 5,
                "image_url": "",
                "item_type": "part",
            }
        ]
        with patch.dict(
            "os.environ", {"REBRICKABLE_API_KEY": "test-key"}
        ), patch.object(
    rebrickable, "fetch_set_inventory", return_value=(set_info, api_parts)
        ):
            page = self.client.get("/inventaire/verifier?set_num=10312")
        self.assertEqual(page.status_code, 200)
        # Les 2 pièces réservées au set à réunir comptent comme possédées.
        self.assertIn(
            b'data-part="3001" data-color="4" data-stock="0" data-sets="2" data-to-buy="3"',
            page.data,
        )
        self.assertIn(
            "<strong>2</strong><span>dans un set</span>".encode("utf-8"), page.data
        )

    def test_add_stock_part_validates_item_type_and_color(self):
        response = self.client.post(
            "/stock",
            data={
                "part_num": "3001",
                "color_id": "4",
                "color_name": "Rouge",
                "quantity": "2",
                "item_type": "banana",
            },
        )
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT item_type FROM stock_parts WHERE part_num = '3001'"
            ).fetchone()
        self.assertEqual(row["item_type"], "part")

        response = self.client.post(
            "/stock",
            data={"part_num": "3002", "color_id": "rouge", "quantity": "1"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Couleur invalide pour cette pièce du vrac.".encode("utf-8"),
            response.data,
        )
        with legolist.database() as connection:
            stored = connection.execute(
                "SELECT 1 FROM stock_parts WHERE part_num = '3002'"
            ).fetchone()
        self.assertIsNone(stored)

    def test_export_button_only_on_the_missing_parts_page(self):
        self.add_set_and_part()
        for path in ("/pieces", "/sets", "/inventaire"):
            page = self.client.get(path).get_data(as_text=True)
            self.assertNotIn("export-link", page)
            self.assertNotIn("export-panel", page)
        missing = self.client.get("/manquantes").get_data(as_text=True)
        self.assertIn('class="export-link"', missing)
        self.assertIn("export-panel", missing)

if __name__ == "__main__":
    unittest.main()
