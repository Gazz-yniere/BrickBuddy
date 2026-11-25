"""Pièces à réunir.

Chaque test pilote l'app par son client de test, sur une base temporaire.
"""

import re
from brickbuddy import colors
import app as legolist
from testbase import SuiteTests

class PiecesTests(SuiteTests):
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

    def test_manual_part_entry_is_only_shown_in_collection(self):
        set_id = self.add_set_and_part()
        gathering_page = self.client.get("/pieces")
        self.assertNotIn("Ajouter des pièces manuellement".encode(), gathering_page.data)
        self.assertIn(b"Mes sets", gathering_page.data)

        self.client.post(f"/sets/{set_id}/collect")
        collection_page = self.client.get("/sets")
        self.assertIn("Ajouter des pièces manuellement".encode(), collection_page.data)
        self.assertIn(
            f'action="/sets/{set_id}/parts"'.encode(), collection_page.data
        )

    def test_collection_part_keeps_full_name_and_color_for_compact_display(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                "UPDATE set_parts SET part_name = ?, color_name = ? WHERE set_id = ?",
                ("A very long brick name <special>", "A very long color", set_id),
            )
        self.client.post(f"/sets/{set_id}/collect")

        page = self.client.get("/sets").get_data(as_text=True)
        self.assertIn('title="A very long brick name &lt;special&gt;"', page)
        self.assertIn('title="Réf. 3001 · A very long color"', page)
        self.assertIn('aria-label="3 pièces manquantes sur 3"', page)
        self.assertIn('<span class="set-missing-count">3</span><span class="part-total">/3</span>', page)
        self.assertNotIn("×3 dans le set", page)
        self.assertIn('class="set-status-form collection-part-controls "', page)
        self.assertIn('name="mark_complete"', page)
        self.assertIn('name="change" value="-1"', page)
        self.assertIn('name="change" value="1"', page)

    def test_collection_parts_are_grouped_by_color_per_set(self):
        set_id = self.add_set_and_part()
        for part_num, color_id, color_name in (
            ("3002", "1", "Bleu"),
            ("3003", "4", "Rouge"),
            ("3004", "1", "Bleu"),
        ):
            response = self.client.post(
                f"/sets/{set_id}/parts",
                data={
                    "part_num": part_num,
                    "part_name": f"Pièce {part_num}",
                    "color_id": color_id,
                    "color_name": color_name,
                    "quantity": "1",
                },
            )
            self.assertEqual(response.status_code, 302)
        self.client.post(f"/sets/{set_id}/collect")

        page = self.client.get("/sets").get_data(as_text=True)
        groups = page.split('<details class="collection-color-group" open>')[1:]
        self.assertEqual(len(groups), 2)
        self.assertIn("<strong>Blue</strong>", groups[0])
        self.assertIn('style="--brick: #0055BF"', groups[0])
        self.assertIn("2 références", groups[0])
        self.assertIn("Réf. 3002", groups[0])
        self.assertIn("Réf. 3004", groups[0])
        self.assertNotIn("Réf. 3001", groups[0])
        self.assertIn("<strong>Red</strong>", groups[1])
        self.assertIn('style="--brick: #C91A09"', groups[1])
        self.assertIn("2 références", groups[1])
        self.assertIn("Réf. 3001", groups[1])
        self.assertIn("Réf. 3003", groups[1])

    def test_a_color_is_listed_once_whatever_its_spelling(self):
        # Une couleur Rebrickable (« Red ») et la même couleur saisie à la main (« rouge »)
        # doivent faire une seule carte sur tous les écrans.
        gathering_id = self.create_gathering_set()
        collected_id = self.create_collected_set()
        for set_id in (gathering_id, collected_id):
            self.insert_set_part(set_id, "3001", color_id=4, color_name="Red", quantity=2)
            self.insert_set_part(set_id, "3002", color_id=4, color_name="rouge", quantity=2)
            self.insert_set_part(set_id, "3003", color_id=1, color_name="Bleu", quantity=1)

        titles = lambda page: re.findall(r'<div class="color-heading"><h3>([^<]+)</h3>', page)
        pieces_page = self.client.get("/pieces").get_data(as_text=True)
        self.assertEqual(titles(pieces_page), ["Blue", "Red"])
        self.assertEqual(pieces_page.count('class="color-card color-group"'), 2)
        self.assertIn('class="color-header" style="--brick: #C91A09"', pieces_page)
        self.assertIn("<h3>Red</h3>", pieces_page)

        missing_page = self.client.get("/manquantes").get_data(as_text=True)
        self.assertEqual(titles(missing_page), ["Blue", "Red"])
        self.assertIn("Réf. 3001 · Red", self.client.get("/sets").get_data(as_text=True))

        # Le filtre et la recherche acceptent n'importe quelle graphie de la même couleur.
        for spelling in ("Rouge", "Red", "rouge"):
            filtered = self.client.get(f"/pieces?color={spelling}").get_data(as_text=True)
            self.assertEqual(filtered.count('class="color-card color-group"'), 1)
            self.assertIn(">3001</strong>", filtered)
            self.assertIn(">3002</strong>", filtered)
            self.assertNotIn(">3003</strong>", filtered)
        searched = self.client.get("/pieces?q=rouge").get_data(as_text=True)
        self.assertIn(">3001</strong>", searched)
        self.assertNotIn(">3003</strong>", searched)

    def test_color_gradients_use_known_colors_and_skip_unknown_colors(self):
        self.assertEqual(colors.lego_color_hex("Red"), "#C91A09")
        self.assertEqual(colors.lego_color_hex("rouge"), "#C91A09")
        self.assertIsNone(colors.lego_color_hex("Figurine"))
        self.assertIsNone(colors.lego_color_hex("Couleur inconnue"))
        # Une seule cle et un seul libellé par couleur, mais deux couleurs distinctes restent distinctes.
        self.assertEqual(colors.color_group_key("Red"), colors.color_group_key("rouge"))
        self.assertEqual(colors.color_group_label("Red"), "Red")
        self.assertNotEqual(colors.color_group_key("Blue"), colors.color_group_key("Dark Blue"))
        self.assertEqual(colors.color_group_label("Dark Blue"), "Dark Blue")

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

    def test_gathering_parts_keep_sort_order_with_completed_parts_last(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.executemany(
                """
                INSERT INTO set_parts
                    (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (set_id, "a", "Alpha", 4, "Rouge", 4, 0),
                    (set_id, "b", "Beta", 4, "Rouge", 2, 1),
                    (set_id, "c", "Charlie", 4, "Rouge", 1, 0),
                    (set_id, "d", "Delta", 4, "Rouge", 5, 2),
                    (set_id, "e", "Echo", 11, "Noir", 1, 1),
                ],
            )
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ? AND part_num = 'b'",
                (set_id,),
            ).fetchone()["id"]

        def red_cards(sort="color"):
            page = self.client.get(f"/pieces?color=Rouge&sort={sort}").get_data(as_text=True)
            return re.findall(
                r'<article class="piece-card[^"]*" data-gathering-order="(\d+)">'
                r'.*?<div class="piece-card-heading">\s*<strong>([^<]+)</strong>',
                page,
                re.DOTALL,
            )

        self.assertEqual(red_cards(), [("1", "b"), ("2", "3001"), ("4", "d"), ("0", "a"), ("3", "c")])
        self.assertEqual(red_cards("quantity"), [("0", "d"), ("2", "3001"), ("3", "b"), ("1", "a"), ("4", "c")])

        response = self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "pieces", "mark_complete": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.get_json()["part_missing"], 0)
        self.assertEqual(red_cards(), [("2", "3001"), ("4", "d"), ("0", "a"), ("1", "b"), ("3", "c")])
        self.client.post(
            f"/parts/{part_id}/missing",
            data={"return_to": "pieces", "change": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(red_cards()[0], ("1", "b"))

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
