"""Notices de montage.

Chaque test pilote l'app par son client de test, sur une base temporaire.
"""

from unittest.mock import patch
import io
from brickbuddy import config
from brickbuddy import instructions
import app as legolist
from testbase import SuiteTests

class NoticesTests(SuiteTests):
    def test_instruction_upload_read_share_and_delete(self):
        set_id = self.add_set_and_part()
        self.client.post(f"/sets/{set_id}/duplicate", data={"return_to": "pieces"})
        with legolist.database() as connection:
            copy = connection.execute(
                "SELECT id FROM sets WHERE set_num = '10312-1' AND id != ?", (set_id,)
            ).fetchone()
        self.assertIsNotNone(copy)
        page = self.client.get(f"/sets/{set_id}/notices")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Construire", self.client.get("/pieces").get_data(as_text=True))
        invalid = self.client.post(
            f"/sets/{set_id}/notices",
            data={"csrf_token": "test-csrf-token", "notice": (io.BytesIO(b"not pdf"), "fake.pdf")},
        )
        self.assertEqual(invalid.status_code, 302)
        self.assertFalse(list((self.db_path.parent / "instructions").glob("*.pdf")))
        pdf = b"%PDF-1.4\nsample\n%%EOF"
        response = self.client.post(
            f"/sets/{set_id}/notices",
            data={"csrf_token": "test-csrf-token", "notice": (io.BytesIO(pdf), "guide.pdf")},
        )
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            notice_id = connection.execute("SELECT id FROM set_instructions").fetchone()["id"]
        copy_id = copy["id"]
        page = self.client.get(f"/sets/{copy_id}/notices").get_data(as_text=True)
        self.assertIn("guide.pdf", page)
        self.assertIn(f"/sets/{copy_id}/notices/{notice_id}/pdf", page)
        self.assertIn(f'src="/sets/{copy_id}/notices/{notice_id}/pdf#page=1&amp;view=FitH&amp;navpanes=0"', page)
        file_response = self.client.get(f"/sets/{copy_id}/notices/{notice_id}/pdf")
        self.assertEqual(file_response.data, pdf)
        self.assertEqual(file_response.mimetype, "application/pdf")
        # La notice est immuable : le navigateur la relit sans revalidation,
        # le lecteur l'affiche donc sans attente.
        self.assertIn("max-age=31536000", file_response.headers["Cache-Control"])
        self.assertIn("immutable", file_response.headers["Cache-Control"])
        self.assertEqual(file_response.headers["Accept-Ranges"], "bytes")
        etag = file_response.headers["ETag"]
        file_response.close()
        cached = self.client.get(
            f"/sets/{copy_id}/notices/{notice_id}/pdf", headers={"If-None-Match": etag}
        )
        self.assertEqual(cached.status_code, 304)
        cached.close()
        partial = self.client.get(
            f"/sets/{copy_id}/notices/{notice_id}/pdf", headers={"Range": "bytes=0-4"}
        )
        self.assertEqual((partial.status_code, partial.data), (206, b"%PDF-"))
        partial.close()
        self.assertEqual(
            self.client.post(f"/sets/{copy_id}/notices/{notice_id}/supprimer").status_code, 400
        )
        self.client.post(
            f"/sets/{copy_id}/notices/{notice_id}/supprimer",
            data={"csrf_token": "test-csrf-token"},
        )
        self.assertEqual(self.client.get(f"/sets/{set_id}/notices/{notice_id}/pdf").status_code, 404)
        self.assertFalse(list((self.db_path.parent / "instructions").glob("*.pdf")))

    def test_official_instruction_search_download_and_reuse(self):
        set_id = self.add_set_and_part()
        url = "https://www.lego.com/cdn/product-assets/product.bi.core.pdf/123.pdf"
        html = (
            f'<a href="{url}">Download</a><a href="{url}">duplicate</a>'
            '<a href="https://evil.example/notice.pdf">wrong</a>'
            '<a href="https://www.lego.com/other.pdf">unrelated</a>'
        ).encode()
        pdf = b"%PDF-1.4\nexample\n%%EOF"

        class FakeResponse(io.BytesIO):
            def __init__(self, data):
                super().__init__(data)
                self.headers = {}

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse(pdf if request.full_url == url else html)

        with patch.object(legolist.urllib.request, "build_opener", return_value=FakeOpener()):
            page = self.client.get(f"/sets/{set_id}/notices?rechercher=1").get_data(as_text=True)
            self.assertEqual(page.count('name="url"'), 1)
            self.assertIn(url, page)
            self.assertNotIn("evil.example", page)
            response = self.client.post(
                f"/sets/{set_id}/notices/telecharger",
                data={"csrf_token": "test-csrf-token", "url": url},
            )
        self.assertEqual(response.status_code, 302)
        with legolist.database() as connection:
            notice_id = connection.execute("SELECT id FROM set_instructions").fetchone()["id"]
        file_response = self.client.get(f"/sets/{set_id}/notices/{notice_id}/pdf")
        self.assertEqual(file_response.data, pdf)
        file_response.close()
        with patch.object(legolist.urllib.request, "build_opener", side_effect=AssertionError("unexpected download")):
            self.client.post(
                f"/sets/{set_id}/notices/telecharger",
                data={"csrf_token": "test-csrf-token", "url": url},
            )
        self.assertEqual(
            self.client.post(
                f"/sets/{set_id}/notices/telecharger",
                data={"csrf_token": "test-csrf-token", "url": "https://evil.example/notice.pdf"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                f"/sets/{set_id}/notices/telecharger",
                data={"csrf_token": "test-csrf-token", "url": "https://www.lego.com:bad/cdn/product-assets/product.bi.core.pdf/x.pdf"},
            ).status_code,
            400,
        )

    def test_build_page_searches_after_display_and_marks_saved_notices(self):
        set_id = self.add_set_and_part()
        url = "https://www.lego.com/cdn/product-assets/product.bi.core.pdf/900.pdf"
        cover = "https://www.lego.com/cdn/product-assets/product.bi.core.img/900.png"
        official = [{"url": url, "title": "Notice 900", "image": cover, "position": 0}]
        with patch.object(
    instructions, "find_lego_instructions", side_effect=AssertionError("la recherche doit être différée")
        ):
            page = self.client.get(f"/sets/{set_id}/notices?construire=1").get_data(as_text=True)
        # La page arrive immédiatement : la recherche est confiée au navigateur.
        self.assertIn('data-auto-search="1"', page)
        self.assertIn(f'data-search-url="/sets/{set_id}/notices/rechercher"', page)
        with patch.object(instructions, "find_lego_instructions", return_value=official) as search:
            results = self.client.get(f"/sets/{set_id}/notices/rechercher").get_data(as_text=True)
        search.assert_called_once_with("10312-1")
        # Une seule notice : pas de bouton « Tout télécharger ».
        self.assertNotIn("data-download-all", results)
        self.assertIn("Télécharger", results)
        self.assertIn(f'src="{cover}"', results)
        self.assertIn("instruction-card-thumb", results)
        self.assertIn("data-download-tile", results)
        self.assertNotIn("<iframe", results)
        self.client.post(
            f"/sets/{set_id}/notices",
            data={"csrf_token": "test-csrf-token", "notice": (io.BytesIO(b"%PDF-1.4"), "manuel.pdf")},
        )
        # Des notices enregistrées n'empêchent pas la recherche automatique.
        with patch.object(
    instructions, "find_lego_instructions", side_effect=AssertionError("la recherche doit être différée")
        ):
            page = self.client.get(f"/sets/{set_id}/notices?construire=1")
        body = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("manuel.pdf", body)
        self.assertIn('data-auto-search="1"', body)
        # La recherche est lancée même quand des notices sont déjà là.
        pdf = b"%PDF-1.4\nexample\n%%EOF"

        class FakeResponse(io.BytesIO):
            def __init__(self, content):
                super().__init__(content)
                self.headers = {}

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse(pdf)

        with patch.object(instructions, "find_lego_instructions", return_value=official), patch.object(
            legolist.urllib.request, "build_opener", return_value=FakeOpener()
        ):
            response = self.client.post(
                f"/sets/{set_id}/notices/telecharger",
                data={"csrf_token": "test-csrf-token", "url": url, "title": "Notice 900", "position": "0"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            payload = response.get_json()
            results = self.client.get(f"/sets/{set_id}/notices/rechercher").get_data(as_text=True)
        # Le serveur renvoie la tuile déjà rendue : le navigateur remplace la
        # proposition par la notice enregistrée, sans recharger la page.
        self.assertTrue(payload["saved"])
        self.assertIn("data-instruction-card", payload["html"])
        self.assertIn("Notice 900", payload["html"])
        self.assertIn(payload["pdf_url"], payload["html"])
        # La notice enregistrée a quitté les propositions, le compte rendu suit.
        self.assertNotIn(url, results)
        self.assertNotIn("data-download-tile", results)
        self.assertIn("2 notices enregistrées", results)
        page = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
        self.assertIn("Notice 900", page)

    def test_several_official_notices_offer_download_all(self):
        set_id = self.add_set_and_part()
        official = [
            {
                "url": f"https://www.lego.com/cdn/product-assets/product.bi.core.pdf/{number}.pdf",
                "title": f"Construction ({index + 1}/2)",
                "image": f"https://www.lego.com/cdn/product-assets/product.bi.core.img/{number}.png",
                "position": index,
            }
            for index, number in enumerate((111, 222))
        ]

        with patch.object(instructions, "find_lego_instructions", return_value=official):
            results = self.client.get(f"/sets/{set_id}/notices/rechercher").get_data(as_text=True)

        self.assertIn("Tout télécharger (2)", results)
        self.assertIn("data-download-all", results)
        self.assertEqual(results.count("data-download-tile"), 2)
        self.assertIn("2 notices disponibles pour ce set", results)

    def test_build_page_merges_panels_and_hides_empty_viewer(self):
        set_id = self.add_set_and_part()
        official = [
            {
                "url": f"https://www.lego.com/cdn/product-assets/product.bi.core.pdf/{number}.pdf",
                "title": f"Construction ({index + 1}/2)",
                "image": f"https://www.lego.com/cdn/product-assets/product.bi.core.img/{number}.png",
                "position": index,
            }
            for index, number in enumerate((311, 322))
        ]
        with patch.object(instructions, "find_lego_instructions", side_effect=AssertionError("différée")):
            page = self.client.get(f"/sets/{set_id}/notices?construire=1").get_data(as_text=True)
        # Un seul panneau pour les notices : plus de bloc « Recherche des notices LEGO ».
        self.assertIn("<h2>Notices du set</h2>", page)
        self.assertNotIn("Recherche des notices LEGO", page)
        self.assertNotIn("Notices enregistrées", page)
        self.assertIn("Aucune notice pour ce set", page)
        # Sans notice, le panneau garde le déclencheur de recherche.
        self.assertIn("data-search-instructions", page)
        self.assertIn("Rechercher les notices", page)
        # Sans notice lisible, le lecteur est présent mais masqué : le premier
        # téléchargement l'affiche sans recharger la page.
        self.assertIn('class="instruction-panel instruction-viewer-band is-hidden"', page)
        self.assertIn("data-instruction-head", page)
        with patch.object(instructions, "find_lego_instructions", return_value=official):
            search = self.client.get(f"/sets/{set_id}/notices?rechercher=1").get_data(as_text=True)
        # Les notices à télécharger entrent dans le carrousel, avec leur bouton.
        self.assertLess(search.index("data-carousel-track"), search.index("data-download-tile"))
        self.assertLess(search.index("data-download-tile"), search.index('data-carousel-arrow="next"'))
        self.assertIn("Télécharger", search)
        self.assertIn("data-download-all", search)
        self.assertIn('class="instruction-panel instruction-viewer-band is-hidden"', search)
        # Aucune notice officielle trouvée : le compte rendu le dit et laisse
        # relancer la recherche.
        with patch.object(instructions, "find_lego_instructions", return_value=[]):
            nothing = self.client.get(f"/sets/{set_id}/notices/rechercher").get_data(as_text=True)
        self.assertIn("Aucune notice officielle trouvée", nothing)
        self.assertIn("Rechercher les notices", nothing)
        self.assertNotIn("data-download-tile", nothing)

    def test_instruction_parser_pairs_cover_image_with_its_card(self):
        html = (
            '<ul>'
            '<li><div><picture><source srcset="https://www.lego.com/cdn/product-assets/'
            'product.bi.core.img/111.png?width=320 320w"></picture>'
            '<h3 id="0">Livre 1</h3></div>'
            '<a href="https://www.lego.com/cdn/product-assets/product.bi.core.pdf/111.pdf" '
            'aria-describedby="0">Télécharger</a></li>'
            '<li><div><picture><source srcset="https://www.lego.com/cdn/product-assets/'
            'product.bi.additional.main.img/10312_FR_BI_Build_Translate.png"></picture>'
            '<h3 id="1">Traduction</h3></div>'
            '<a href="https://www.lego.com/cdn/product-assets/product.bi.core.pdf/222.pdf" '
            'aria-describedby="1">Télécharger</a></li>'
            '</ul>'
        )
        parser = instructions.LegoInstructionParser()
        parser.feed(html)
        manuals = parser.instructions()
        self.assertEqual(
            manuals[0]["image"],
            "https://www.lego.com/cdn/product-assets/product.bi.core.img/111.png",
        )
        self.assertEqual(manuals[0]["title"], "Livre 1")
        # Une planche de traduction n'est pas une couverture de notice.
        self.assertEqual(manuals[1]["image"], "")
        self.assertEqual(manuals[1]["title"], "Traduction")

    def test_ajax_instruction_download_returns_json(self):
        set_id = self.add_set_and_part()
        url = "https://www.lego.com/cdn/product-assets/product.bi.core.pdf/456.pdf"

        class FakeResponse(io.BytesIO):
            def __init__(self, content):
                super().__init__(content)
                self.headers = {}

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse(b"%PDF-1.4\n%%EOF")

        with patch.object(legolist.urllib.request, "build_opener", return_value=FakeOpener()):
            response = self.client.post(
                f"/sets/{set_id}/notices/telecharger",
                data={"csrf_token": "test-csrf-token", "url": url, "search_return": "1"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["saved"])
        with legolist.database() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM set_instructions").fetchone()[0], 1)

    def test_manual_upload_offers_a_dropzone(self):
        set_id = self.add_set_and_part()
        page = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
        # Le champ fichier brut est remplace par une zone de depot : libelle
        # explicite, nom du fichier choisi, « Ajouter » actif seulement avec un PDF.
        self.assertIn("instruction-dropzone", page)
        self.assertIn("data-file-input", page)
        self.assertIn("data-file-name", page)
        self.assertIn("Choisir un PDF", page)
        self.assertIn("Aucun fichier choisi", page)
        self.assertIn('<button class="button button-primary" type="submit" disabled>Ajouter</button>', page)
        self.assertNotIn('<label for="notice">Fichier PDF</label>', page)
        scripts = self.client.get("/static/js/instructions.js").get_data(as_text=True)
        self.assertIn("data-file-input", scripts)
        self.assertIn("data-dropzone", scripts)
        self.assertIn("uploadManualInstruction", scripts)

    def test_ajax_manual_upload_keeps_the_found_books(self):
        set_id = self.add_set_and_part()
        official = [
            {
                "url": f"https://www.lego.com/cdn/product-assets/product.bi.core.pdf/{number}.pdf",
                "title": f"Livre {index + 1}",
                "image": "",
                "position": index,
            }
            for index, number in enumerate((811, 822))
        ]
        with patch.object(instructions, "find_lego_instructions", return_value=official):
            results = self.client.get(f"/sets/{set_id}/notices/rechercher").get_data(as_text=True)
        self.assertEqual(results.count("data-download-tile"), 2)
        # L'ajout d'un PDF manuel renvoie sa carte : la liste des livres trouves
        # n'est pas rechargee et garde ses numeros.
        payload = self.client.post(
            f"/sets/{set_id}/notices",
            data={
                "csrf_token": "test-csrf-token",
                "notice": (io.BytesIO(b"%PDF-1.4\n%%EOF"), "notice-manuelle.pdf"),
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        ).get_json()
        self.assertTrue(payload["saved"])
        self.assertIn('<span class="instruction-card-position">Ajout 1</span>', payload["html"])
        self.assertIn("notice-manuelle.pdf", payload["html"])
        page = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
        self.assertIn('<span class="instruction-card-position">Ajout 1</span>', page)
        # Un deuxieme ajout manuel est numrote a part, sans empieter sur les livres LEGO.
        self.client.post(
            f"/sets/{set_id}/notices",
            data={
                "csrf_token": "test-csrf-token",
                "notice": (io.BytesIO(b"%PDF-1.4\n%%EOF"), "autre.pdf"),
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        page = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
        self.assertIn('<span class="instruction-card-position">Ajout 2</span>', page)

    def test_instruction_failures_do_not_leave_partial_files(self):
        set_id = self.add_set_and_part()
        with patch.object(config, "MAX_INSTRUCTION_BYTES", 10):
            response = self.client.post(
                f"/sets/{set_id}/notices",
                data={"csrf_token": "test-csrf-token", "notice": (io.BytesIO(b"%PDF-too-large"), "big.pdf")},
                follow_redirects=True,
            )
        self.assertIn("dépasse", response.get_data(as_text=True))
        with legolist.database() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM set_instructions").fetchone()[0], 0)
        self.assertFalse(list((self.db_path.parent / "instructions").iterdir()))
        class IncompleteResponse(io.BytesIO):
            headers = {"Content-Length": "50"}

        class IncompleteOpener:
            def open(self, request, timeout):
                return IncompleteResponse(b"%PDF-incomplete")

        with patch.object(legolist.urllib.request, "build_opener", return_value=IncompleteOpener()):
            response = self.client.post(
                f"/sets/{set_id}/notices/telecharger",
                data={
                    "csrf_token": "test-csrf-token",
                    "url": "https://www.lego.com/cdn/product-assets/product.bi.core.pdf/123.pdf",
                },
                follow_redirects=True,
            )
        self.assertIn("incomplet", response.get_data(as_text=True))
        self.assertFalse(list((self.db_path.parent / "instructions").iterdir()))
        with patch.object(instructions, "find_lego_instructions", side_effect=RuntimeError("Service indisponible")):
            response = self.client.get(f"/sets/{set_id}/notices?rechercher=1")
        self.assertIn("Service indisponible", response.get_data(as_text=True))
        self.assertEqual(self.client.get("/sets/999999/notices").status_code, 404)

    def test_multiple_official_books_keep_order_and_allow_navigation(self):
        set_id = self.add_set_and_part()
        urls = [
            f"https://www.lego.com/cdn/product-assets/product.bi.core.pdf/{number}.pdf"
            for number in (111, 222)
        ]
        html = "".join(
            f'<h3 id="{index}">Construction ({index + 1}/2)</h3>'
            f'<a aria-describedby="{index}" href="{url}">Télécharger</a>'
            for index, url in enumerate(urls)
        ).encode()

        class FakeResponse(io.BytesIO):
            def __init__(self, content):
                super().__init__(content)
                self.headers = {}

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse(b"%PDF-1.4\n%%EOF" if request.full_url in urls else html)

        with patch.object(legolist.urllib.request, "build_opener", return_value=FakeOpener()):
            search = self.client.get(f"/sets/{set_id}/notices?rechercher=1").get_data(as_text=True)
            self.assertIn("Construction (1/2)", search)
            self.assertIn("Construction (2/2)", search)
            for index in (1, 0):
                response = self.client.post(
                    f"/sets/{set_id}/notices/telecharger",
                    data={
                        "csrf_token": "test-csrf-token", "url": urls[index],
                        "title": f"Construction ({index + 1}/2)", "position": str(index),
                        "search_return": "1",
                    },
                    follow_redirects=True,
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("Construction (1/2)", response.get_data(as_text=True))
            page = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
            self.assertLess(page.index("Construction (1/2)"), page.index("Construction (2/2)"))
            # Plusieurs notices : flèches de navigation intégrées aux tuiles.
            self.assertIn('aria-label="Notice suivante"', page)
            self.assertIn('aria-label="Notice précédente"', page)
            self.assertNotIn("instruction-navigation", page)
            # Les notices officielles enregistrées montrent leur couverture LEGO.
            self.assertIn("cdn/product-assets/product.bi.core.img/", page)
            self.assertIn("instruction-card-thumb", page)
            with legolist.database() as connection:
                rows = connection.execute(
                    "SELECT id, source_position FROM set_instructions ORDER BY source_position"
                ).fetchall()
            second = self.client.get(f"/sets/{set_id}/notices?notice={rows[1]['id']}").get_data(as_text=True)
            self.assertIn(f'notice={rows[0]["id"]}" aria-label="Notice précédente"', second)
            self.assertIn(f"/sets/{set_id}/notices/{rows[1]['id']}/pdf", second)
            self.assertIn("Construction (2/2)", second)
            # L'astuce « Ouvrir » est affichée au-dessus du lecteur.
            self.assertLess(second.index("Si la notice ne s'affiche pas"), second.index("<iframe"))
            file_response = self.client.get(f"/sets/{set_id}/notices/{rows[1]['id']}/pdf")
            self.assertTrue(file_response.data.startswith(b"%PDF-"))
            file_response.close()
            saved = self.client.get(f"/sets/{set_id}/notices?rechercher=1").get_data(as_text=True)
            # Les deux livres sont enregistrés : le compte rendu le dit, plus de tuile à télécharger.
            self.assertIn("2 notices enregistrées", saved)
            self.assertNotIn("data-download-tile", saved)
            self.client.post(
                f"/sets/{set_id}/notices/{rows[0]['id']}/supprimer",
                data={"csrf_token": "test-csrf-token"},
            )
            after_delete = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
            # Une seule notice : les flèches restent en place mais sont masquées.
            self.assertIn('data-carousel-arrow="next" hidden', after_delete)
            self.assertIn('data-carousel-arrow="previous" hidden', after_delete)
            self.assertIn(f"/sets/{set_id}/notices/{rows[1]['id']}/pdf", after_delete)

    def test_viewer_band_matches_panel_width_and_notices_prefetch(self):
        set_id = self.add_set_and_part()
        pdf = b"%PDF-1.4\n%%EOF"
        self.client.post(
            f"/sets/{set_id}/notices",
            data={"csrf_token": "test-csrf-token", "notice": (io.BytesIO(pdf), "guide.pdf")},
        )
        page = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
        # Le lecteur est un panneau de la page : meme largeur que les autres blocs.
        self.assertIn('class="instruction-panel instruction-viewer-band"', page)
        # Plus de largeur « toute la zone » calculee par le navigateur : la bande
        # ne depasse jamais la zone de contenu, donc rien ne casse entre deux pages.
        self.assertNotIn("--main-area-width", page)
        css = self.client.get("/static/css/instructions.css").get_data(as_text=True)
        self.assertIn(".instruction-viewer-band", css)
        self.assertNotIn("--main-area-width", css)
        self.assertNotIn("margin-left: calc(50%", css)
        # Les notices sont preloades : changer de livre ne demande pas d'attente.
        # La taille du fichier est annoncee pour eviter de telecharger un gros
        # PDF pendant que la page est au repos.
        self.assertIn(f'data-pdf-size="{len(pdf)}"', page)
        scripts = self.client.get("/static/js/instructions.js").get_data(as_text=True)
        self.assertIn("prefetchInstructionCard", scripts)
        self.assertIn("PREFETCH_LIMIT_BYTES", scripts)

    def test_instruction_tiles_stack_buttons_and_follow_the_theme(self):
        set_id = self.add_set_and_part()
        pdf = b"%PDF-1.4\n%%EOF"
        self.client.post(
            f"/sets/{set_id}/notices",
            data={"csrf_token": "test-csrf-token", "notice": (io.BytesIO(pdf), "guide.pdf")},
        )
        page = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
        # Dans une tuile, « Ouvrir » est toujours au-dessus de « Retirer » :
        # les boutons sont empiles, de meme largeur, ils ne sortent pas de la carte.
        card = page[page.index("data-instruction-card"):]
        card = card[: card.index("</article>")]
        self.assertLess(card.index("Ouvrir"), card.index("Retirer"))
        css = self.client.get("/static/css/instructions.css").get_data(as_text=True)
        # Dans une tuile, les boutons sont empiles dans une seule colonne.
        self.assertIn(".instruction-card-actions {", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", css)
        self.assertIn(".instruction-card-actions .button { width: 100%;", css)
        # Le lecteur reprend le fond du site, pas un noir plus sombre, et sa
        # boite est celle des autres panneaux de la page.
        self.assertIn("padding: 14px; background: var(--bg)", css)
        self.assertIn("background-color: var(--bg); color-scheme: dark; }", css)
        # Le CSS ne vit plus que dans les feuilles : aucun gabarit n'ecrit de style.
        self.assertNotIn("<style", page)
        self.assertNotIn("<noscript", page)
        # Le livre lu est place a une largeur et demie du bord gauche du carrousel,
        # et borne pour tenir entier dans le carrousel : jamais coupe au bord.
        scripts = self.client.get("/static/js/instructions.js").get_data(as_text=True)
        self.assertIn("placeInstructionCard", scripts)
        self.assertIn("1.5 * lead", scripts)
        self.assertIn("cardLeft + card.offsetWidth - view", scripts)
        self.assertNotIn("card.offsetLeft - (track.clientWidth", scripts)
        # L'accrochage du carrousel re-centrait le livre lu et le coupait : il ne
        # doit pas revenir.
        self.assertNotIn("scroll-snap", css)
        self.assertNotIn("scrollSnapType", scripts)

    def test_multiple_manual_books_sort_naturally_and_migrate_existing_notices(self):
        set_id = self.add_set_and_part()
        with legolist.database() as connection:
            connection.execute("DROP TABLE set_instructions")
            connection.execute(
                """CREATE TABLE set_instructions (
                   id TEXT PRIMARY KEY, set_num TEXT NOT NULL, filename TEXT NOT NULL,
                   source_url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
            )
            connection.execute(
                "INSERT INTO set_instructions (id, set_num, filename) VALUES (?, ?, ?)",
                ("a" * 32, "10312-1", "livre 10.pdf"),
            )
        legolist.initialize_database()
        for name in ("livre 2.pdf", "livre 1.pdf"):
            self.client.post(
                f"/sets/{set_id}/notices",
                data={"csrf_token": "test-csrf-token", "notice": (io.BytesIO(b"%PDF-1.4"), name)},
            )
        page = self.client.get(f"/sets/{set_id}/notices").get_data(as_text=True)
        self.assertLess(page.index("livre 1.pdf"), page.index("livre 2.pdf"))
        self.assertLess(page.index("livre 2.pdf"), page.index("livre 10.pdf"))
        self.assertIn("Notice suivante", page)
