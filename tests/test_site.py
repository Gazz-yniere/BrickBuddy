"""Site : routes, styles, couche dynamique.

Chaque test pilote l'app par son client de test, sur une base temporaire.
"""

from brickbuddy.flask_app import app
import app as legolist
from testbase import SuiteTests

class SiteTests(SuiteTests):
    def test_home_shows_the_collection_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Ma collection", page)
        # L'accueil est la page d'entrée : il mène à chaque écran de la collection.
        for path in ("/sets", "/pieces", "/inventaire", "/manquantes", "/parametres"):
            self.assertIn(f'href="{path}"', page)
        self.assertEqual(self.client.get("/sets").status_code, 200)
        self.assertEqual(self.client.get("/inventaire").status_code, 200)
        self.assertEqual(self.client.get("/manquantes").status_code, 200)

    def test_sidebar_ends_with_settings_then_logout(self):
        page = self.client.get("/pieces").get_data(as_text=True)
        # La note et le profil du bas du menu ne servaient à rien : ils ont disparu.
        self.assertNotIn('class="sidebar-note"', page)
        self.assertNotIn('class="profile"', page)
        self.assertIn('class="sidebar-bottom"', page)
        self.assertLess(page.index('href="/parametres"'), page.index('action="/logout"'))

    def test_topbar_carries_only_the_page_name(self):
        page = self.client.get("/pieces").get_data(as_text=True)
        self.assertIn('class="topbar-title"', page)
        self.assertIn("data-page-title>PIÈCES À RÉUNIR", page)
        # « MON ATELIER » et l'eyebrow de la page ne portent plus le nom de l'écran.
        self.assertNotIn("MON ATELIER", page)
        self.assertNotIn('<div class="eyebrow"><span>', page)

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

    def test_health_endpoint_checks_database_and_returns_json(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_pages_load_the_variables_then_the_shared_sheets_then_the_page(self):
        page = self.client.get("/pieces").get_data(as_text=True)
        # variables.css porte les couleurs, les feuilles partagées le layout et
        # les composants, la feuille de l'écran vient après, le responsive en dernier.
        for sheet in (
            "css/variables.css",
            "css/critical.css",
            "css/base.css",
            "css/layout.css",
            "css/components.css",
            "css/pieces.css",
            "css/responsive.css",
        ):
            self.assertIn(f"static/{sheet}", page)
        self.assertLess(page.index("css/variables.css"), page.index("css/base.css"))
        self.assertLess(page.index("css/components.css"), page.index("css/pieces.css"))
        self.assertLess(page.index("css/pieces.css"), page.index("css/responsive.css"))
        # Seules les polices sont chargées en différé : les feuilles locales sont bloquantes.
        self.assertEqual(page.count('media="print"'), 1)
        self.assertIn("fonts.googleapis.com", page.split('media="print"')[0])
        self.assertNotIn("static/css/", page.split('media="print"')[0])
        # Aucun gabarit n'écrit de CSS : tout vit dans les feuilles.
        self.assertNotIn("<style", page)
        for script in ("js/core.js", "js/inventory.js", "js/instructions.js", "js/images.js"):
            self.assertIn(f"static/{script}", page)
        # core.js est chargé en premier : les autres fichiers s'appuient sur lui.
        self.assertLess(page.index("js/core.js"), page.index("js/instructions.js"))
        # L'écran de connexion charge les feuilles partagées et la sienne, pas celles des écrans.
        anonymous = app.test_client()
        login = anonymous.get("/login").get_data(as_text=True)
        for sheet in ("css/variables.css", "css/base.css", "css/layout.css", "css/login.css"):
            self.assertIn(f"static/{sheet}", login)
        self.assertNotIn("css/pieces.css", login)
        self.assertNotIn("<style", login)

    def test_filters_and_writes_update_without_reloading_the_page(self):
        self.add_set_and_part()
        pieces = self.client.get("/pieces").get_data(as_text=True)
        # La zone que la couche commune remplace, et la déconnexion qui reste
        # une navigation normale (elle doit vider la session).
        self.assertIn('class="content-area" data-page-results', pieces)
        self.assertIn('<form action="/logout" method="post" data-static>', pieces)
        inventory_page = self.client.get("/inventaire").get_data(as_text=True)
        self.assertIn('class="origin-chip is-active" data-dynamic', inventory_page)
        self.assertIn('href="/manquantes" data-dynamic', self.client.get("/manquantes?sort=missing").get_data(as_text=True))
        scripts = self.client.get("/static/js/core.js").get_data(as_text=True)
        self.assertIn('[data-page-results]', scripts)
        self.assertIn('matches("[data-static]")', scripts)
        self.assertIn('a[data-dynamic]', scripts)
        # La popin de confirmation est son propre comportement : son formulaire
        # `method="dialog"` ferme le <dialog>, ce n'est pas une action sur la page.
        self.assertIn('matches("[method=\\"dialog\\"]")', scripts)
        self.assertIn('<form method="dialog"', pieces)
        # Une action en JSON redemande la page : les compteurs suivent, sans rechargement.
        self.assertIn("async function refreshCurrentPage()", scripts)
        self.assertIn("await refreshCurrentPage()", self.client.get("/static/js/inventory.js").get_data(as_text=True))
        # Rien ne recharge la page d'elle-même : aucune relève ne la redemande.
        self.assertNotIn("watchPriceRefresh", scripts)
        self.assertNotIn("watchBackgroundRefresh", scripts)
