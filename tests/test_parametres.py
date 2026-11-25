"""Paramètres : clés enregistrées localement, taux de change relevé tout seul."""

from unittest.mock import patch
import time
import app as legolist
from brickbuddy import config
from brickbuddy import rates
from brickbuddy import settings
from testbase import ImmediateThread
from testbase import SilentThread
from testbase import SuiteTests


class ParametresTests(SuiteTests):
    def test_saved_key_is_never_shown_or_logged(self):
        with self.capture_logs() as logged:
            self.client.post(
                "/parametres",
                data={
                    "csrf_token": "test-csrf-token",
                    "REBRICKABLE_API_KEY": "cle-secrete",
                    "BRICKOWL_API_KEY": "cle-brickowl-secrete",
                    "SHOW_PRICES": "on",
                },
            )
            page = self.client.get("/parametres").get_data(as_text=True)

        self.assertEqual(settings.setting("REBRICKABLE_API_KEY"), "cle-secrete")
        self.assertIn("Enregistrée dans l'app", page)
        self.assertNotIn("cle-secrete", page)
        self.assertNotIn("cle-brickowl-secrete", page)
        self.assertNotIn("cle-secrete", logged())
        self.assertIn("REBRICKABLE_API_KEY", logged())

    def test_saved_setting_beats_the_env_file_and_an_empty_field_removes_it(self):
        with patch.dict("os.environ", {"REBRICKABLE_API_KEY": "cle-du-fichier"}, clear=False):
            self.client.post(
                "/parametres",
                data={
                    "csrf_token": "test-csrf-token",
                    "REBRICKABLE_API_KEY": "cle-de-la-base",
                    "SHOW_PRICES": "on",
                },
            )
            self.assertEqual(settings.setting_value("REBRICKABLE_API_KEY"), "cle-de-la-base")

            # Un champ vide retire l'override : l'option revient au fichier .env.
            self.client.post(
                "/parametres",
                data={"csrf_token": "test-csrf-token", "REBRICKABLE_API_KEY": ""},
            )
            self.assertEqual(settings.setting_value("REBRICKABLE_API_KEY"), "cle-du-fichier")
            self.assertEqual(settings.setting("REBRICKABLE_API_KEY"), "")

    def test_show_prices_checkbox_is_saved_even_unchecked(self):
        with patch.dict("os.environ", {"SHOW_PRICES": "true"}, clear=False):
            self.client.post(
                "/parametres",
                data={"csrf_token": "test-csrf-token", "REBRICKABLE_API_KEY": "cle"},
            )
            # Le case-à-coche décoché est enregistré : il désactive, il ne « revient » pas au .env.
            self.assertFalse(settings.flag("SHOW_PRICES"))

            self.client.post(
                "/parametres",
                data={"csrf_token": "test-csrf-token", "SHOW_PRICES": "on"},
            )
            self.assertTrue(settings.flag("SHOW_PRICES"))

    def test_settings_form_requires_the_session_token(self):
        response = self.client.post("/parametres", data={"REBRICKABLE_API_KEY": "cle"})
        self.assertEqual(response.status_code, 400)

    def test_rate_is_refreshed_once_a_day_and_stored(self):
        calls = []

        def payload():
            calls.append(1)
            return {"rates": {"EUR": 1.2}}

        with patch.object(rates, "rate_payload", payload), patch.object(
            legolist.threading, "Thread", ImmediateThread
        ):
            self.assertTrue(rates.claim_rate_refresh())
            self.assertEqual(len(calls), 1)
            self.assertEqual(rates.current_rate(), 1.2)
            self.assertEqual(rates.rate_refresh_date(), time.strftime("%d/%m/%Y"))
            # Le relevé du jour n'est pas redemandé à chaque affichage de page.
            self.assertFalse(rates.claim_rate_refresh())
            self.assertEqual(len(calls), 1)

    def test_unreachable_rate_service_keeps_the_known_rate(self):
        def unreachable():
            raise OSError("service injoignable")

        with patch.object(rates, "rate_payload", unreachable), patch.object(
            legolist.threading, "Thread", ImmediateThread
        ):
            self.assertTrue(rates.claim_rate_refresh())
            self.assertEqual(rates.current_rate(), config.DEFAULT_GBP_EUR_RATE)
            # L'échec est horodaté : le service n'est pas relancé à chaque page.
            self.assertFalse(rates.claim_rate_refresh())

    def test_rate_button_forces_a_new_refresh(self):
        calls = []

        def payload():
            calls.append(1)
            return {"rates": {"EUR": 1.35}}

        with patch.object(rates, "rate_payload", payload), patch.object(
            legolist.threading, "Thread", ImmediateThread
        ):
            rates.request_rate_refresh()
            self.assertEqual(len(calls), 1)
            response = self.client.post("/parametres/taux", data={"csrf_token": "test-csrf-token"})
            self.assertEqual(response.status_code, 302)
            # Le bouton force un relevé, même quand celui du jour est déjà passé.
            self.assertEqual(len(calls), 2)
            self.assertEqual(rates.current_rate(), 1.35)

    def test_home_page_launches_the_daily_rate_refresh(self):
        calls = []

        def payload():
            calls.append(1)
            return {"rates": {"EUR": 1.2}}

        with patch.object(rates, "rate_payload", payload), patch.object(
            legolist.threading, "Thread", ImmediateThread
        ):
            self.client.get("/")
            self.assertEqual(len(calls), 1)
            self.assertEqual(rates.current_rate(), 1.2)
            # La page d'entrée ne relance pas le relevé du jour déjà passé.
            self.client.get("/")
            self.assertEqual(len(calls), 1)

    def test_rate_button_is_polite_while_a_refresh_runs(self):
        with patch.object(legolist.threading, "Thread", SilentThread):
            self.assertTrue(rates.claim_rate_refresh(force=True))
            self.assertEqual(
                self.client.post("/parametres/taux", data={"csrf_token": "test-csrf-token"}).status_code,
                302,
            )
            page = self.client.get("/parametres").get_data(as_text=True)

        self.assertIn("Un relevé du taux est déjà en cours", page)
        self.assertIn("Relevé en cours…", page)

    def test_rate_button_confirms_the_new_rate(self):
        def payload():
            return {"rates": {"EUR": 1.24}}

        with patch.object(rates, "rate_payload", payload), patch.object(
            legolist.threading, "Thread", SilentThread
        ):
            response = self.client.post(
                "/parametres/taux", data={"csrf_token": "test-csrf-token"}, follow_redirects=True
            )
        page = response.get_data(as_text=True)
        # Le bouton répond en direct : la page confirme le taux relevé dans la requête.
        self.assertIn("Taux mis à jour : 1,240 € pour 1 £.", page)
        self.assertIn("1,240 € pour 1 £", page)
        self.assertEqual(rates.current_rate(), 1.24)

    def test_rate_button_reports_a_failed_refresh(self):
        def unreachable():
            raise OSError("service injoignable")

        with patch.object(rates, "rate_payload", unreachable), patch.object(
            legolist.threading, "Thread", SilentThread
        ):
            response = self.client.post(
                "/parametres/taux", data={"csrf_token": "test-csrf-token"}, follow_redirects=True
            )
        page = response.get_data(as_text=True)
        # Le bouton échoue en direct : la page dit que le taux connu est gardé.
        self.assertIn("Le service de change", page)
        self.assertIn("le taux connu est conservé", page)
        self.assertEqual(rates.current_rate(), 1.18)
