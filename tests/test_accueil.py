"""Accueil : le tableau de bord de toute la collection."""

from unittest.mock import patch
import app as legolist
from testbase import SilentThread
from testbase import SuiteTests


class AccueilTests(SuiteTests):
    def test_dashboard_counts_every_part_of_the_collection(self):
        collected_id = self.create_collected_set()
        self.insert_set_part(collected_id, "3001", color_id=4, quantity=3, missing_quantity=2)
        gathering_id = self.create_gathering_set()
        self.insert_set_part(gathering_id, "3002", color_id=1, quantity=4)
        self.add_stock_part("3003", color_id=4, quantity=7)

        page = self.client.get("/").get_data(as_text=True)
        self.assertEqual(page.count('class="dash-card"'), 6)
        self.assertIn("<strong>1</strong><span>sets différents</span>", page)
        self.assertIn("<strong>4</strong><span>pièces à trouver</span>", page)
        self.assertIn("<strong>7</strong><span>en vrac</span>", page)
        self.assertIn("<strong>2</strong><span>pièces à acheter</span>", page)
        self.assertIn("<strong>1</strong><span>références à acheter</span>", page)

    def test_dashboard_value_appears_only_when_prices_are_enabled(self):
        self.own_a_part()
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Les prix ne sont pas activés", page)

        with patch.dict("os.environ", self.price_env, clear=False), patch.object(
            legolist.threading, "Thread", SilentThread
        ):
            self.record_price("3001", "4", "0.42")
            priced = self.client.get("/").get_data(as_text=True)

        # 0,42 £ × 3 pièces × 1,5 £/€ : la carte « valeur estimée » apparaît.
        self.assertIn("<span>valeur des pièces connues</span>", priced)
        self.assertIn("2 €", priced)
