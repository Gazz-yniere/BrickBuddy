"""Sets : ajout, collecte, duplications.

Chaque test pilote l'app par son client de test, sur une base temporaire.
"""

from pathlib import Path
from unittest.mock import patch
import io
from brickbuddy import db
from brickbuddy import instructions
from brickbuddy import rebrickable
import app as legolist
from testbase import SuiteTests

class SetsTests(SuiteTests):
    def test_book_numbers_stay_stable_across_download_and_removal(self):
        set_id = self.add_set_and_part()
        official = [
            {
                "url": f"https://www.lego.com/cdn/product-assets/product.bi.core.pdf/{number}.pdf",
                "title": f"Livre {index + 1}",
                "image": "",
                "position": index,
            }
            for index, number in enumerate((711, 722))
        ]

        class FakeResponse(io.BytesIO):
            def __init__(self, content):
                super().__init__(content)
                self.headers = {}

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse(b"%PDF-1.4\n%%EOF")

        with patch.object(instructions, "find_lego_instructions", return_value=official), patch.object(
            legolist.urllib.request, "build_opener", return_value=FakeOpener()
        ):
            # Le numero affiche est celui de la liste LEGO, telechargee ou non :
            # la carte enregistree reprend le numero de la proposition.
            payload = self.client.post(
                f"/sets/{set_id}/notices/telecharger",
                data={
                    "csrf_token": "test-csrf-token",
                    "url": official[1]["url"],
                    "title": official[1]["title"],
                    "position": "1",
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
            ).get_json()
            self.assertIn('<span class="instruction-card-position">Livre 2</span>', payload["html"])
            page = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
            self.assertIn('<span class="instruction-card-position">Livre 2</span>', page)
            self.assertNotIn('<span class="instruction-card-position">Livre 1</span>', page)
            # Retirer la notice la rend a la liste LEGO : la proposition retrouve
            # son numero, la page n'est pas rechargee et la liste reste complete.
            delete_response = self.client.post(
                f"/sets/{set_id}/notices/{payload['notice_id']}/supprimer",
                data={"csrf_token": "test-csrf-token"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        result = delete_response.get_json()
        self.assertTrue(result["deleted"])
        self.assertIn("data-download-tile", result["tile_html"])
        self.assertIn('data-position="1"', result["tile_html"])
        self.assertIn("Livre 2", result["tile_html"])
        self.assertIn("product.bi.core.pdf/722.pdf", result["tile_html"])

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
    rebrickable,
    "fetch_set_inventory",
                return_value=({"name": "Set importé", "set_img_url": ""}, imported_parts),
            ):
                with patch.object(
    rebrickable, "fetch_minifig_parts_for_set", return_value=[]
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

    def test_removing_a_searched_set_removes_it_and_its_parts(self):
        # Un set ni dans Mes sets ni en recherche n'apparait sur aucun écran :
        # le « × » le retire avec ses pièces, sans laisser de ligne invisible.
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute(
                "UPDATE sets SET set_image_url = ? WHERE id = ?",
                ("https://example.test/10312.jpg", set_id),
            )
        page = self.client.get("/pieces").data
        self.assertIn(b'class="set-avatar"><img', page)
        self.assertIn(b"https://example.test/10312.jpg", page)
        # L'action détruit des données : la popin de confirmation la garde.
        self.assertIn(b"Retirer ce set et ses pi\xc3\xa8ces ?", page)

        response = self.client.post(
            f"/sets/{set_id}/gathering",
            data={"in_gathering": "0", "return_to": "pieces"},
        )

        self.assertEqual(response.headers["Location"], "/pieces")
        self.assertNotIn(f'data-set-id="{set_id}"'.encode(), self.client.get("/pieces").data)
        self.assertNotIn(b"Supprimer ce set", self.client.get("/pieces").data)
        with legolist.database() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM sets WHERE id = ?", (set_id,)).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM set_parts WHERE set_id = ?", (set_id,)).fetchone()[0],
                0,
            )
        self.client.post("/sets", data={"set_num": "10312"})
        self.assertNotIn(b"exemplaire 2", self.client.get("/pieces").data)

    def test_unsearching_an_owned_set_keeps_its_data(self):
        # Un set possédé quitte la recherche mais reste dans Mes sets.
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        self.client.post(
            f"/sets/{set_id}/gathering",
            data={"in_gathering": "0", "return_to": "sets"},
        )

        page = self.client.get("/sets").data
        self.assertIn(f'data-set-id="{set_id}"'.encode(), page)
        with legolist.database() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM set_parts WHERE set_id = ?", (set_id,)
                ).fetchone()[0],
                1,
            )

    def test_no_action_leaves_a_set_without_any_screen(self):
        # Vendre, retirer de Mes sets, retirer de la recherche : aucune ligne
        # que nul écran n'affiche ne doit survivre.
        owned_id = self.add_set_and_part()
        self.client.post(f"/sets/{owned_id}/collect")
        searched_id = self.add_set_and_part()
        self.client.post(f"/sets/{searched_id}/uncollect")
        self.client.post(f"/sets/{owned_id}/sold")
        self.client.post(
            f"/sets/{searched_id}/gathering",
            data={"in_gathering": "0", "return_to": "pieces"},
        )
        with legolist.database() as connection:
            invisible = connection.execute(
                """
                SELECT COUNT(*) FROM sets
                WHERE in_collection = 0 AND in_gathering = 0
                """
            ).fetchone()[0]
            orphans = connection.execute(
                """
                SELECT COUNT(*) FROM set_parts
                WHERE set_id NOT IN (SELECT id FROM sets)
                """
            ).fetchone()[0]
            minifig_orphans = connection.execute(
                """
                SELECT COUNT(*) FROM minifig_parts
                WHERE set_id NOT IN (SELECT id FROM sets)
                """
            ).fetchone()[0]
        self.assertEqual(invisible, 0)
        self.assertEqual(orphans, 0)
        self.assertEqual(minifig_orphans, 0)

    def test_selling_a_copy_removes_that_copy_and_its_parts(self):
        # Deux exemplaires d'un même set : vendre l'un ne touche pas l'autre.
        first_id = self.add_set_and_part()
        self.client.post(f"/sets/{first_id}/collect")
        with legolist.database() as connection:
            part_id = connection.execute(
                "SELECT id FROM set_parts WHERE set_id = ?", (first_id,)
            ).fetchone()["id"]
        self.client.post(
            f"/parts/{part_id}/missing", data={"missing_quantity": "0", "return_to": "sets"}
        )
        self.client.post(f"/sets/{first_id}/duplicate", data={"return_to": "sets"})
        with legolist.database() as connection:
            second_id = connection.execute(
                "SELECT MAX(id) FROM sets"
            ).fetchone()[0]

        self.client.post(f"/sets/{second_id}/sold")

        with legolist.database() as connection:
            remaining = connection.execute(
                """
                SELECT s.id, COUNT(p.id) AS parts
                FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
                GROUP BY s.id
                """
            ).fetchall()
        self.assertEqual([row["id"] for row in remaining], [first_id])
        self.assertEqual(remaining[0]["parts"], 1)
        page = self.client.get("/sets").data
        self.assertIn(f'data-set-id="{first_id}"'.encode(), page)
        self.assertNotIn(f'data-set-id="{second_id}"'.encode(), page)
        inventory_page = self.client.get("/inventaire").get_data(as_text=True)
        self.assertEqual(inventory_page.count('class="inventory-part-card"'), 1)
        self.assertIn('data-total="3"', inventory_page)

    def test_selling_a_copy_keeps_the_notice_shared_by_the_set_number(self):
        # La notice est partagée par référence : vendre un exemplaire ne la retire pas.
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        self.client.post(f"/sets/{set_id}/duplicate", data={"return_to": "sets"})
        with legolist.database() as connection:
            second_id = connection.execute(
                "SELECT id FROM sets WHERE id != ?", (set_id,)
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO set_instructions (id, set_num, filename)
                VALUES ('gardee', '10312-1', '10312.pdf')
                """
            )

        self.client.post(f"/sets/{second_id}/sold")

        with legolist.database() as connection:
            kept = connection.execute(
                "SELECT set_num FROM set_instructions WHERE id = 'gardee'"
            ).fetchone()
        self.assertIsNotNone(kept)
        self.assertEqual(kept["set_num"], "10312-1")

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

    def test_existing_database_sets_migrate_as_not_owned(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        with patch.object(db, "DATABASE_PATH", legacy_path):
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
        with patch.object(db, "DATABASE_PATH", legacy_path):
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

    def test_set_parts_table_has_item_type_defaulting_to_part(self):
        with legolist.database() as connection:
            columns = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_info(set_parts)")
            }
        self.assertIn("item_type", columns)
        self.assertEqual(columns["item_type"]["dflt_value"], "'part'")
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            row = connection.execute(
                "SELECT item_type FROM set_parts WHERE set_id = ?", (set_id,)
            ).fetchone()
        self.assertEqual(row["item_type"], "part")

    def test_set_cards_show_a_notice_badge_that_follows_the_saved_notices(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/collect")
        # Aucune notice enregistrée : la pastille le dit, sans ouvrir la carte.
        empty = self.client.get("/sets").get_data(as_text=True)
        self.assertIn('class="set-instructions is-empty"', empty)
        self.assertIn("Pas de notice", empty)
        self.client.post(
            f"/sets/{set_id}/notices",
            data={"csrf_token": "test-csrf-token", "notice": (io.BytesIO(b"%PDF-1.4\n%%EOF"), "guide.pdf")},
        )
        page = self.client.get("/sets").get_data(as_text=True)
        self.assertIn('aria-label="1 notice enregistrée pour ce set"', page)
        self.assertIn("1 notice", page)
        self.assertNotIn("Pas de notice", page)
        with legolist.database() as connection:
            notice_id = connection.execute("SELECT id FROM set_instructions").fetchone()["id"]
        self.client.post(
            f"/sets/{set_id}/notices/{notice_id}/supprimer",
            data={"csrf_token": "test-csrf-token"},
        )
        # La dernière notice retirée : la pastille revient en état vide.
        self.assertIn("Pas de notice", self.client.get("/sets").get_data(as_text=True))
