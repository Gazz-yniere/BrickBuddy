"""Déploiement : sauvegarde de la base avant une mise à jour, image Docker complète.

Chaque test pilote l'app sur une base temporaire, comme les autres fichiers de tests.
"""
import contextlib
import sqlite3
from pathlib import Path

from brickbuddy import backup
from testbase import SuiteTests

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DeploiementTests(SuiteTests):
    def test_backup_copies_the_live_database(self):
        self.add_stock_part("3001", quantity=7)
        target = backup.backup_database()
        # La copie porte le nom attendu par le manuel d'installation, à côté de la base.
        self.assertEqual(target, self.db_path.parent / "bdd.bak")
        self.assertTrue(target.exists())
        with contextlib.closing(sqlite3.connect(target)) as copy:
            self.assertEqual(copy.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            # La copie est un fichier seul : rien à reporter au moment de restaurer.
            self.assertEqual(copy.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            self.assertEqual(
                copy.execute("SELECT part_num, quantity FROM stock_parts").fetchall(),
                [("3001", 7)],
            )
        self.assertFalse([p for p in self.db_path.parent.iterdir() if p.name.startswith("bdd.bak-")])

    def test_backup_refuses_a_missing_database(self):
        self.db_path.unlink()
        with self.assertRaises(FileNotFoundError):
            backup.backup_database()

    def test_image_ships_the_application_package(self):
        # L'app est découpée en modules : sans eux dans l'image, rien ne démarre.
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY brickbuddy ./brickbuddy", dockerfile)
        compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("brickbuddy.backup", compose)
        self.assertIn("brickbuddy:", compose)

    def test_no_module_imports_a_library_outside_requirements(self):
        # L'image installe seulement requirements.txt : une import non listé la casse.
        listed = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("Flask", listed)
        for module in (PROJECT_ROOT / "brickbuddy").rglob("*.py"):
            self.assertNotIn("import requests", module.read_text(encoding="utf-8"), module.name)
