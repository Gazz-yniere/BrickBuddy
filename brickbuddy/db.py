"""Base SQLite : connexion, schéma, compteurs de la barre latérale."""
from . import config
from .flask_app import app
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3

DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", config.BASE_DIR / "data" / "legolist.db"))



@app.context_processor
def navigation_stats():
    with database() as connection:
        stats = connection.execute(
            """
            SELECT COUNT(DISTINCT s.id) AS set_count,
                   COALESCE(SUM(p.missing_quantity), 0) AS missing_count
            FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
            WHERE s.in_collection = 1
            """
        ).fetchone()
    return {"nav_stats": dict(stats)}



@contextmanager
def database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # Deux workers gunicorn partagent la base : on attend patiemment un verrou
    # au lieu d'échouer, et le mode journal WAL laisse les lectures se faire
    # pendant qu'une écriture est en cours.
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()



def initialize_database():
    with database() as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        # WAL : les pages se lisent pendant les écritures (2 workers gunicorn),
        # l'écriture du journal est bien plus rapide que le mode « rollback ».
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sets (
                id INTEGER PRIMARY KEY,
                set_num TEXT NOT NULL,
                title TEXT NOT NULL,
                set_image_url TEXT NOT NULL DEFAULT '',
                theme_name TEXT NOT NULL DEFAULT 'Thème non renseigné',
                year INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS set_parts (
                id INTEGER PRIMARY KEY,
                set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
                part_num TEXT NOT NULL,
                part_name TEXT NOT NULL,
                color_id INTEGER NOT NULL DEFAULT 0,
                color_name TEXT NOT NULL DEFAULT 'Unknown',
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                missing_quantity INTEGER NOT NULL CHECK(missing_quantity >= 0),
                image_url TEXT NOT NULL DEFAULT '',
                item_type TEXT NOT NULL DEFAULT 'part',
                UNIQUE(set_id, part_num, color_id)
            );
            CREATE TABLE IF NOT EXISTS set_instructions (
                id TEXT PRIMARY KEY,
                set_num TEXT NOT NULL,
                filename TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                display_title TEXT NOT NULL DEFAULT '',
                source_position INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS minifig_parts (
                id INTEGER PRIMARY KEY,
                set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
                fig_num TEXT NOT NULL,
                part_num TEXT NOT NULL,
                part_name TEXT NOT NULL,
                color_id INTEGER NOT NULL,
                color_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                missing_quantity INTEGER NOT NULL DEFAULT 0 CHECK(missing_quantity >= 0),
                tracking_version INTEGER NOT NULL DEFAULT 1,
                image_url TEXT NOT NULL DEFAULT '',
                UNIQUE(set_id, fig_num, part_num, color_id)
            );
            CREATE INDEX IF NOT EXISTS idx_minifig_parts_set_fig ON minifig_parts(set_id, fig_num);
            CREATE INDEX IF NOT EXISTS idx_sets_set_num ON sets(set_num);
            CREATE INDEX IF NOT EXISTS idx_set_instructions_set_num ON set_instructions(set_num);
            CREATE TABLE IF NOT EXISTS stock_parts (
                id INTEGER PRIMARY KEY,
                part_num TEXT NOT NULL,
                part_name TEXT NOT NULL,
                color_id INTEGER NOT NULL DEFAULT 0,
                color_name TEXT NOT NULL DEFAULT 'Unknown',
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                image_url TEXT NOT NULL DEFAULT '',
                item_type TEXT NOT NULL DEFAULT 'part',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(part_num, color_id)
            );
            CREATE INDEX IF NOT EXISTS idx_stock_parts_key ON stock_parts(part_num, color_id);
            CREATE TABLE IF NOT EXISTS rebrickable_request_gate (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                next_request_at REAL NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO rebrickable_request_gate (id, next_request_at)
                VALUES (1, 0);
            CREATE TABLE IF NOT EXISTS rebrickable_image_cache (
                image_key TEXT PRIMARY KEY,
                source_url TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS brickowl_request_gate (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                next_request_at REAL NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO brickowl_request_gate (id, next_request_at)
                VALUES (1, 0);
            CREATE TABLE IF NOT EXISTS part_boids (
                part_num TEXT NOT NULL,
                color_id INTEGER NOT NULL DEFAULT 0,
                boid TEXT NOT NULL,
                PRIMARY KEY (part_num, color_id)
            );
            CREATE TABLE IF NOT EXISTS part_prices (
                part_num TEXT NOT NULL,
                color_id INTEGER NOT NULL DEFAULT 0,
                boid TEXT NOT NULL DEFAULT '',
                price_gbp REAL NOT NULL DEFAULT 0 CHECK(price_gbp >= 0),
                fetched_at REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (part_num, color_id)
            );
            CREATE TABLE IF NOT EXISTS price_refresh_state (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                last_refresh_date TEXT NOT NULL DEFAULT '',
                running_since REAL NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO price_refresh_state (id, last_refresh_date, running_since)
                VALUES (1, '', 0);
            CREATE TABLE IF NOT EXISTS app_settings (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS exchange_rate (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                rate REAL NOT NULL DEFAULT 0,
                fetched_at REAL NOT NULL DEFAULT 0,
                running_since REAL NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO exchange_rate (id, rate, fetched_at, running_since)
                VALUES (1, 0, 0, 0);
            """
        )
        connection.execute("DROP TABLE IF EXISTS buildable_search_cache")
        connection.execute("DROP TABLE IF EXISTS buildable_theme_cache")
        connection.execute("DROP TABLE IF EXISTS buildable_inventory_cache")
        instruction_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(set_instructions)")
        }
        if "display_title" not in instruction_columns:
            connection.execute(
                "ALTER TABLE set_instructions ADD COLUMN display_title TEXT NOT NULL DEFAULT ''"
            )
        if "source_position" not in instruction_columns:
            connection.execute("ALTER TABLE set_instructions ADD COLUMN source_position INTEGER")
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(sets)")
        }
        if "in_collection" not in columns:
            connection.execute(
                "ALTER TABLE sets ADD COLUMN in_collection INTEGER NOT NULL DEFAULT 0 "
                "CHECK(in_collection IN (0, 1))"
            )
        if "in_gathering" not in columns:
            connection.execute(
                "ALTER TABLE sets ADD COLUMN in_gathering INTEGER NOT NULL DEFAULT 0 "
                "CHECK(in_gathering IN (0, 1))"
            )
            connection.execute(
                "UPDATE sets SET in_gathering = 1 WHERE in_collection = 0"
            )
        if "all_parts_found" not in columns:
            connection.execute(
                "ALTER TABLE sets ADD COLUMN all_parts_found INTEGER NOT NULL DEFAULT 0 "
                "CHECK(all_parts_found IN (0, 1))"
            )
        if "set_image_url" not in columns:
            connection.execute(
                "ALTER TABLE sets ADD COLUMN set_image_url TEXT NOT NULL DEFAULT ''"
            )
        if "theme_name" not in columns:
            connection.execute(
                "ALTER TABLE sets ADD COLUMN theme_name TEXT NOT NULL DEFAULT 'Thème non renseigné'"
            )
        if "year" not in columns:
            connection.execute("ALTER TABLE sets ADD COLUMN year INTEGER")
        part_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(set_parts)")
        }
        if "item_type" not in part_columns:
            connection.execute(
                "ALTER TABLE set_parts ADD COLUMN item_type TEXT NOT NULL DEFAULT 'part'"
            )
        minifig_part_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(minifig_parts)")
        }
        if "missing_quantity" not in minifig_part_columns:
            connection.execute(
                "ALTER TABLE minifig_parts ADD COLUMN missing_quantity "
                "INTEGER NOT NULL DEFAULT 0 CHECK(missing_quantity >= 0)"
            )
            connection.execute(
                "UPDATE minifig_parts SET missing_quantity = quantity"
            )
        if "tracking_version" not in minifig_part_columns:
            connection.execute(
                "ALTER TABLE minifig_parts ADD COLUMN tracking_version INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(
            """
            UPDATE minifig_parts
            SET missing_quantity = CASE
                WHEN (SELECT p.missing_quantity FROM set_parts p
                      WHERE p.set_id = minifig_parts.set_id
                        AND p.part_num = minifig_parts.fig_num
                        AND p.item_type = 'minifig') = 0 THEN 0
                ELSE missing_quantity * COALESCE(
                    (SELECT p.missing_quantity FROM set_parts p
                     WHERE p.set_id = minifig_parts.set_id
                       AND p.part_num = minifig_parts.fig_num
                       AND p.item_type = 'minifig'), 1)
                END,
                tracking_version = 1
            WHERE tracking_version = 0
            """
        )
        connection.execute(
            """
            UPDATE set_parts
            SET missing_quantity = (
                SELECT MIN(set_parts.quantity, MAX(
                    (mp.missing_quantity + mp.quantity - 1) / mp.quantity))
                FROM minifig_parts mp
                WHERE mp.set_id = set_parts.set_id AND mp.fig_num = set_parts.part_num
            )
            WHERE item_type = 'minifig' AND EXISTS (
                SELECT 1 FROM minifig_parts mp
                WHERE mp.set_id = set_parts.set_id AND mp.fig_num = set_parts.part_num
            )
            """
        )
        connection.execute(
            """
            UPDATE sets
            SET year = (
                SELECT source.year FROM sets source
                WHERE source.set_num = sets.set_num AND source.year IS NOT NULL
                ORDER BY source.id
                LIMIT 1
            )
            WHERE year IS NULL AND EXISTS (
                SELECT 1 FROM sets source
                WHERE source.set_num = sets.set_num AND source.year IS NOT NULL
            )
            """
        )
        unique_set_number = any(
            index["unique"]
            and [
                column["name"]
                for column in connection.execute(
                    f"PRAGMA index_info({index['name']})"
                )
            ] == ["set_num"]
            for index in connection.execute("PRAGMA index_list(sets)").fetchall()
        )
        if unique_set_number:
            connection.execute(
                """
                CREATE TABLE sets_without_unique_number (
                    id INTEGER PRIMARY KEY,
                    set_num TEXT NOT NULL,
                    title TEXT NOT NULL,
                    set_image_url TEXT NOT NULL DEFAULT '',
                    theme_name TEXT NOT NULL DEFAULT 'Thème non renseigné',
                    year INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    in_collection INTEGER NOT NULL DEFAULT 0
                        CHECK(in_collection IN (0, 1)),
                    in_gathering INTEGER NOT NULL DEFAULT 1
                        CHECK(in_gathering IN (0, 1)),
                    all_parts_found INTEGER NOT NULL DEFAULT 0
                        CHECK(all_parts_found IN (0, 1))
                )
                """
            )
            connection.execute(
                """
                INSERT INTO sets_without_unique_number
                    (id, set_num, title, set_image_url, theme_name, year, created_at, in_collection, in_gathering, all_parts_found)
                SELECT id, set_num, title, set_image_url, theme_name, year, created_at, in_collection, in_gathering, all_parts_found
                FROM sets
                """
            )
            connection.execute("DROP TABLE sets")
            connection.execute(
                "ALTER TABLE sets_without_unique_number RENAME TO sets"
            )
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise sqlite3.IntegrityError("La migration des sets a cassé des relations de pièces.")
