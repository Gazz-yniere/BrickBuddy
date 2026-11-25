"""Connexion et sessions.

Chaque test pilote l'app par son client de test, sur une base temporaire.
"""

from unittest.mock import patch
from brickbuddy.flask_app import app
import app as legolist
from testbase import SuiteTests

class ConnexionTests(SuiteTests):
    def test_login_protects_pages_and_accepts_the_shared_password(self):
        client = app.test_client()
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
            client = app.test_client()
            client.get("/login")
            with client.session_transaction() as browser_session:
                csrf_token = browser_session["csrf_token"]
            response = client.post(
                "/login",
                data={"csrf_token": csrf_token, "password": password},
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/pieces")

    def test_login_rejects_wrong_password_and_requires_csrf(self):
        client = app.test_client()
        login_page = client.get("/login")
        self.assertEqual(login_page.status_code, 200)
        with client.session_transaction() as browser_session:
            csrf_token = browser_session["csrf_token"]

        invalid_csrf = client.post(
            "/login", data={"csrf_token": "wrong-token", "password": "test-password"}
        )
        self.assertEqual(invalid_csrf.status_code, 400)
        for _ in range(6):
            response = client.post(
                "/login",
                data={"csrf_token": csrf_token, "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)
            self.assertIn("Mot de passe incorrect.", response.get_data(as_text=True))
            self.assertNotIn(
                "Trop de tentatives", response.get_data(as_text=True)
            )

        response = client.post(
            "/login",
            data={"csrf_token": csrf_token, "password": "test-password-123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/pieces")

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
        client = app.test_client()
        with patch.dict("os.environ", {"APP_PASSWORD": ""}):
            response = client.get("/login")
            self.assertEqual(response.status_code, 503)
            self.assertIn(b"connexion n&#39;est pas encore configur", response.data)
            protected = client.get("/pieces")
            self.assertEqual(protected.status_code, 302)
