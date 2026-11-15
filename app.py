import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, abort, flash, g, jsonify, make_response, redirect, render_template, request, send_file, session, url_for


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "data" / "legolist.db"))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").casefold()
    in {"1", "true", "yes", "on"},
)

# Couleurs LEGO officielles (noms Rebrickable -> hexadecimal RGB).
# Source : https://rebrickable.com/colors/ (273 couleurs, capture du 30/10/2026).
LEGO_COLOR_HEX = {
    "Black": "#05131D",
    "White": "#FFFFFF",
    "Red": "#C91A09",
    "Blue": "#0055BF",
    "Green": "#237841",
    "Yellow": "#F2CD37",
    "Orange": "#FE8A18",
    "Dark Orange": "#A95500",
    "Medium Orange": "#FFA70B",
    "Bright Light Orange": "#F8BB3D",
    "Light Orange": "#F9BA61",
    "Very Light Orange": "#F3CF9B",
    "Dark Red": "#720E0F",
    "Brown": "#583927",
    "Reddish Brown": "#582A12",
    "Dark Brown": "#352100",
    "Light Brown": "#7C503A",
    "Medium Brown": "#755945",
    "Tan": "#E4CD9E",
    "Dark Tan": "#958A73",
    "Light Tan": "#F3C988",
    "Nougat": "#D09168",
    "Light Nougat": "#F6D7B3",
    "Medium Nougat": "#AA7D55",
    "Dark Nougat": "#AD6140",
    "Pink": "#FC97AC",
    "Light Pink": "#FECCCF",
    "Bright Pink": "#E4ADC8",
    "Dark Pink": "#C870A0",
    "Medium Dark Pink": "#F785B1",
    "Light Salmon": "#FEBABD",
    "Salmon": "#F2705E",
    "Coral": "#FF698F",
    "Bright Reddish Orange": "#EE5434",
    "Reddish Orange": "#CA4C0B",
    "Sand Red": "#D67572",
    "Earth Orange": "#FA9C1C",
    "Rust": "#B31004",
    "Magenta": "#923978",
    "Purple": "#81007B",
    "Dark Purple": "#3F3691",
    "Light Purple": "#CD6298",
    "Medium Violet": "#9391E4",
    "Violet": "#4354A3",
    "Dark Blue-Violet": "#2032B0",
    "Medium Bluish Violet": "#6874CA",
    "Lavender": "#E1D5ED",
    "Medium Lavender": "#AC78BA",
    "Light Lilac": "#9195CA",
    "Reddish Lilac": "#8E5597",
    "Sand Purple": "#845E84",
    "Lime": "#BBE90B",
    "Medium Lime": "#C7D23C",
    "Light Lime": "#D9E4A7",
    "Yellowish Green": "#DFEEA5",
    "Olive Green": "#9B9A5A",
    "Bright Green": "#4B9F4A",
    "Medium Green": "#73DCA1",
    "Light Green": "#C2DAB8",
    "Sand Green": "#A0BCAC",
    "Dark Green": "#184632",
    "Bright Light Yellow": "#FFF03A",
    "Light Yellow": "#FBE696",
    "Dark Turquoise": "#008F9B",
    "Light Turquoise": "#55A5AF",
    "Aqua": "#B3D7D1",
    "Light Aqua": "#ADC3C0",
    "Sky Blue": "#7DBFDD",
    "Medium Azure": "#36AEBF",
    "Dark Azure": "#078BC9",
    "Maersk Blue": "#3592C3",
    "Pastel Blue": "#5AC4DA",
    "Light Blue": "#B4D2E3",
    "Bright Light Blue": "#9FC3E9",
    "Medium Blue": "#5A93DB",
    "Dark Blue": "#0A3463",
    "Royal Blue": "#4C61DB",
    "Sand Blue": "#6074A1",
    "Light Bluish Gray": "#A0A5A9",
    "Dark Bluish Gray": "#6C6E68",
    "Light Gray": "#9BA19D",
    "Dark Gray": "#6D6E5C",
    "Very Light Bluish Gray": "#E6E3E0",
    "Very Light Gray": "#E6E3DA",
    "Milky White": "#FFFFFF",
    "Trans-Clear": "#FCFCFC",
    "Trans-Black": "#635F52",
    "Trans-Brown": "#635F52",
    "Trans-Black IR Lens": "#635F52",
    "Trans-Red": "#C91A09",
    "Trans-Yellow": "#F5CD2F",
    "Trans-Neon Yellow": "#DAB000",
    "Trans-Neon Green": "#F8F184",
    "Trans-Neon Orange": "#FF800D",
    "Trans-Neon Red": "#FF0040",
    "Trans-Orange": "#F08F1C",
    "Trans-Flame Yellowish Orange": "#FCB76D",
    "Trans-Fire Yellow": "#FBE890",
    "Trans-Dark Blue": "#0020A0",
    "Trans-Medium Blue": "#CFE2F7",
    "Trans-Light Blue": "#AEEFEC",
    "Trans-Very Lt Blue": "#C1DFF0",
    "Trans-Light Royal Blue": "#B4D4F7",
    "Trans-Green": "#84B68D",
    "Trans-Bright Green": "#D9E4A7",
    "Trans-Light Bright Green": "#C9E788",
    "Trans-Light Green": "#94E5AB",
    "Trans-Purple": "#A5A5CB",
    "Trans-Medium Purple": "#8D73B3",
    "Trans-Light Purple": "#96709F",
    "Trans-Dark Pink": "#DF6695",
    "Trans-Pink": "#E4ADC8",
    "Glitter Trans-Clear": "#FFFFFF",
    "Glitter Trans-Orange": "#F08F1C",
    "Glitter Trans-Bright Green": "#D9E4A7",
    "Glitter Trans-Neon Green": "#C0F500",
    "Glitter Trans-Light Blue": "#68BCC5",
    "Glitter Trans-Purple": "#A5A5CB",
    "Glitter Trans-Medium Purple": "#8D73B3",
    "Glitter Trans-Pink": "#E4ADC8",
    "Glitter Trans-Green": "#84B68D",
    "Glitter Trans-Dark Pink": "#DF6695",
    "Opal Trans-Clear": "#FCFCFC",
    "Opal Trans-Brown": "#583927",
    "Opal Trans-Yellow": "#F5CD2F",
    "Opal Trans-Bright Green": "#84B68D",
    "Opal Trans-Light Blue": "#68BCC5",
    "Opal Trans-Dark Blue": "#0020A0",
    "Opal Trans-Dark Pink": "#CE1D9B",
    "Opal Trans-Purple": "#8320B7",
    "Glow In Dark Trans": "#BDC6AD",
    "Flat Silver": "#898788",
    "Flat Dark Gold": "#B48455",
    "Metallic Silver": "#A5A9B4",
    "Metallic Green": "#899B5F",
    "Metallic Gold": "#DBAC34",
    "Metallic Copper": "#764D3B",
    "Metal": "#A5ADB4",
    "Chrome Silver": "#E0E0E0",
    "Chrome Gold": "#BBA53D",
    "Chrome Antique Brass": "#645A4C",
    "Chrome Blue": "#6C96BF",
    "Chrome Green": "#3CB371",
    "Chrome Pink": "#AA4D8E",
    "Chrome Black": "#1B2A34",
    "Chrome Red": "#CE3021",
    "Copper": "#AE7A59",
    "Reddish Gold": "#AC8247",
    "Speckle Black-Copper": "#05131D",
    "Speckle Black-Silver": "#05131D",
    "Speckle Black-Gold": "#05131D",
    "Speckle DBGray-Silver": "#6C6E68",
    "Pearl Light Gray": "#9CA3A8",
    "Pearl Dark Gray": "#575857",
    "Pearl Very Light Gray": "#ABADAC",
    "Pearl White": "#F2F3F2",
    "Pearl Gold": "#AA7F2E",
    "Pearl Light Gold": "#DCBC81",
    "Pearl Copper": "#B46A00",
    "Pearl Brown": "#57392C",
    "Pearl Black": "#0A1327",
    "Pearl Blue": "#0059A3",
    "Pearl Green": "#008E3C",
    "Pearl Red": "#D60026",
    "Pearl Lime": "#6A7944",
    "Pearl Sand Blue": "#7988A1",
    "Pearl Titanium": "#3E3C39",
    "Glow In Dark Opaque": "#D4D5C9",
    "Glow in Dark White": "#D9D9D9",
}

# Couleurs sans brique reelle : pas de degrade possible sur les en-tetes.
COLORS_WITHOUT_HEX = {"", "Figurine", "[No Color/Any Color]"}


def lego_color_hex(color_name):
    if not color_name or color_name in COLORS_WITHOUT_HEX:
        return None
    return LEGO_COLOR_HEX.get(color_name)


def authentication_config_error():
    secret_key = app.secret_key
    if (
        not isinstance(secret_key, str)
        or len(secret_key) < 32
        or "replace-with" in secret_key.casefold()
        or "change-me" in secret_key.casefold()
    ):
        return "SECRET_KEY n'est pas configurée avec une valeur aléatoire."

    password = os.environ.get("APP_PASSWORD", "")
    if len(password) < 12 or password.casefold().startswith("replace-with"):
        return "APP_PASSWORD doit contenir au moins 12 caractères et être personnalisé."
    return None


def safe_redirect_target(target):
    if not target:
        return url_for("pieces_page")
    parsed = urllib.parse.urlsplit(target)
    if (
        target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
        and not parsed.scheme
        and not parsed.netloc
    ):
        return target
    return url_for("pieces_page")


def authentication_version():
    password = os.environ["APP_PASSWORD"]
    return hmac.new(
        app.secret_key.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@app.before_request
def require_login():
    if request.endpoint in {"login", "login_submit", "health", "static"}:
        return None
    config_error = authentication_config_error()
    if config_error:
        return redirect(url_for("login", next=request.path))
    if (
        not session.get("authenticated")
        or not hmac.compare_digest(
            session.get("auth_version", ""), authentication_version()
        )
    ):
        next_target = request.full_path if request.query_string else request.path
        return redirect(url_for("login", next=next_target))
    if request.method == "POST":
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        source = urllib.parse.urlsplit(origin or referer or "")
        if (origin or referer) and source.netloc != request.host:
            abort(403)
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return None


@app.get("/login")
def login():
    config_error = authentication_config_error()
    if config_error:
        app.logger.error("Authentication is unavailable: %s", config_error)
        return render_template(
            "login.html",
            config_error="La connexion n'est pas encore configurée. Consultez le README pour configurer l'accès.",
        ), 503

    next_target = safe_redirect_target(request.args.get("next", ""))
    if session.get("authenticated"):
        if hmac.compare_digest(
            session.get("auth_version", ""), authentication_version()
        ):
            return redirect(next_target)
        session.clear()
    csrf_token = session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return render_template(
        "login.html",
        next_target=next_target,
        csrf_token=csrf_token,
        error=None,
        config_error=None,
    )


@app.post("/login")
def login_submit():
    config_error = authentication_config_error()
    if config_error:
        app.logger.error("Authentication is unavailable: %s", config_error)
        return render_template(
            "login.html",
            config_error="La connexion n'est pas encore configurée. Consultez le README pour configurer l'accès.",
        ), 503

    csrf_token = session.get("csrf_token", "")
    submitted_csrf = request.form.get("csrf_token", "")
    if not csrf_token or not hmac.compare_digest(csrf_token, submitted_csrf):
        abort(400, description="Formulaire de connexion expiré. Rechargez la page.")

    password_matches = hmac.compare_digest(
        os.environ["APP_PASSWORD"].encode("utf-8"),
        request.form.get("password", "").encode("utf-8"),
    )

    if not password_matches:
        app.logger.warning("Rejected login attempt")
        return render_template(
            "login.html",
            next_target=safe_redirect_target(request.form.get("next", "")),
            csrf_token=csrf_token,
            error="Mot de passe incorrect.",
            config_error=None,
        ), 401

    session.clear()
    session.permanent = True
    session["authenticated"] = True
    session["auth_version"] = authentication_version()
    session["csrf_token"] = secrets.token_urlsafe(32)
    return redirect(safe_redirect_target(request.form.get("next", "")))


@app.post("/logout")
def logout():
    csrf_token = session.get("csrf_token", "")
    submitted_csrf = request.form.get("csrf_token", "")
    if not csrf_token or not hmac.compare_digest(csrf_token, submitted_csrf):
        abort(400, description="Formulaire de déconnexion expiré. Rechargez la page.")
    session.clear()
    return redirect(url_for("login"))


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
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


ALLOWED_IMAGE_HOSTS = {
    "cdn.rebrickable.com",
    "images.rebrickable.com",
    "rebrickable.com",
    "www.rebrickable.com",
}
IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
IMAGE_SIGNATURES = {
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    "image/gif": lambda data: data.startswith((b"GIF87a", b"GIF89a")),
}
MAX_CACHED_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_CACHE_PATH = Path(
    os.environ.get(
        "IMAGE_CACHE_PATH",
        str(DATABASE_PATH.parent / "rebrickable-images"),
    )
)


def local_image_url(source_url):
    if not source_url:
        return ""
    pending_images = getattr(g, "pending_rebrickable_images", None)
    if pending_images is not None and source_url in pending_images:
        image_key = pending_images[source_url]
        return url_for("cached_rebrickable_image", image_key=image_key)

    parsed = urllib.parse.urlparse(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_IMAGE_HOSTS
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        return source_url
    image_key = hashlib.sha256(source_url.encode("utf-8")).hexdigest()

    if pending_images is None:
        pending_images = {}
        g.pending_rebrickable_images = pending_images
    pending_images[source_url] = image_key
    return url_for("cached_rebrickable_image", image_key=image_key)


@app.after_request
def cache_rebrickable_image_urls(response):
    pending_images = getattr(g, "pending_rebrickable_images", None)
    if pending_images:
        with database() as connection:
            connection.executemany(
                """
                INSERT INTO rebrickable_image_cache (image_key, source_url)
                VALUES (?, ?)
                ON CONFLICT(image_key) DO NOTHING
                """,
                (
                    (image_key, source_url)
                    for source_url, image_key in pending_images.items()
                ),
            )
    return response


app.jinja_env.filters["local_image_url"] = local_image_url


@app.get("/media/rebrickable/<image_key>")
def cached_rebrickable_image(image_key):
    if not re.fullmatch(r"[a-f0-9]{64}", image_key):
        abort(404)
    with database() as connection:
        cached = connection.execute(
            """
            SELECT source_url, content_type FROM rebrickable_image_cache
            WHERE image_key = ?
            """,
            (image_key,),
        ).fetchone()
    if cached is None:
        abort(404)

    content_type = cached["content_type"]
    extension = IMAGE_TYPES.get(content_type)
    image_path = IMAGE_CACHE_PATH / f"{image_key}{extension}" if extension else None
    if image_path and image_path.is_file():
        return send_file(
            image_path,
            mimetype=content_type,
            conditional=True,
            max_age=31536000,
        )

    source_url = cached["source_url"]
    parsed = urllib.parse.urlparse(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_IMAGE_HOSTS
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        abort(404)
    req = urllib.request.Request(source_url, headers={"User-Agent": "LegoList/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            final_url = urllib.parse.urlparse(response.geturl())
            if (
                final_url.scheme != "https"
                or final_url.hostname not in ALLOWED_IMAGE_HOSTS
                or final_url.port not in (None, 443)
                or final_url.username
                or final_url.password
            ):
                raise ValueError("Le serveur d'image a redirigé vers un domaine non autorisé.")
            declared_content_type = response.headers.get_content_type()
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_CACHED_IMAGE_BYTES:
                raise ValueError("L'image Rebrickable dépasse la taille maximale autorisée.")
            image_bytes = response.read(MAX_CACHED_IMAGE_BYTES + 1)
            if len(image_bytes) > MAX_CACHED_IMAGE_BYTES:
                raise ValueError("L'image Rebrickable dépasse la taille maximale autorisée.")
            content_type = next(
                (
                    image_type
                    for image_type, signature_check in IMAGE_SIGNATURES.items()
                    if signature_check(image_bytes)
                ),
                None,
            )
            if content_type is None:
                raise ValueError(
                    "Le contenu reçu n'est pas un format d'image reconnu."
                )
            if declared_content_type != content_type:
                app.logger.info(
                    "Type d'image Rebrickable corrigé : %s annoncé, %s détecté.",
                    declared_content_type,
                    content_type,
                )
            extension = IMAGE_TYPES[content_type]
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
        app.logger.warning("Impossible de mettre en cache une image Rebrickable: %s", error)
        return Response("Image Rebrickable indisponible.", status=502, mimetype="text/plain")

    IMAGE_CACHE_PATH.mkdir(parents=True, exist_ok=True)
    image_path = IMAGE_CACHE_PATH / f"{image_key}{extension}"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=IMAGE_CACHE_PATH, prefix=f"{image_key}.", suffix=".tmp", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(image_bytes)
        os.replace(temporary_path, image_path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
    with database() as connection:
        connection.execute(
            "UPDATE rebrickable_image_cache SET content_type = ? WHERE image_key = ?",
            (content_type, image_key),
        )
    return send_file(
        image_path,
        mimetype=content_type,
        conditional=True,
        max_age=31536000,
    )


def initialize_database():
    with database() as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
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
            """
        )
        connection.execute("DROP TABLE IF EXISTS buildable_search_cache")
        connection.execute("DROP TABLE IF EXISTS buildable_theme_cache")
        connection.execute("DROP TABLE IF EXISTS buildable_inventory_cache")
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


def rebrickable_get(path):
    api_key = os.environ.get("REBRICKABLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Ajoutez REBRICKABLE_API_KEY dans le fichier .env pour importer automatiquement les pièces.")

    separator = "&" if "?" in path else "?"
    url = f"https://rebrickable.com/api/v3/lego/{path}{separator}{urllib.parse.urlencode({'key': api_key})}"
    req = urllib.request.Request(url, headers={"User-Agent": "LegoList/1.0"})
    with database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = time.time()
        next_request_at = connection.execute(
            "SELECT next_request_at FROM rebrickable_request_gate WHERE id = 1"
        ).fetchone()["next_request_at"]
        request_at = max(now, next_request_at)
        connection.execute(
            "UPDATE rebrickable_request_gate SET next_request_at = ? WHERE id = 1",
            (request_at + 1.1,),
        )
    time.sleep(max(0, request_at - now))
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 404:
            raise ValueError("Référence de set introuvable sur Rebrickable.") from error
        if error.code in (401, 403):
            raise ValueError("La clé Rebrickable est invalide ou n'a pas accès à l'API.") from error
        if error.code == 429:
            raise RuntimeError(
                "Rebrickable a limité les requêtes. L'opération est arrêtée sans nouvelle tentative ; réessaie plus tard."
            ) from error
        raise RuntimeError(f"Rebrickable a répondu avec l'erreur {error.code}.") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("Impossible de joindre Rebrickable. Vérifiez votre connexion puis réessayez.") from error


def fetch_set_info(set_num):
    return rebrickable_get(f"sets/{urllib.parse.quote(set_num, safe='-')}/")


def fetch_theme_name(theme_id):
    theme = rebrickable_get(f"themes/{int(theme_id)}/")
    return theme.get("name") or f"Thème {theme_id}"


def fetch_set_inventory(set_num):
    set_info = fetch_set_info(set_num)
    parts = {}
    next_page = f"sets/{urllib.parse.quote(set_num, safe='-')}/parts/?page_size=1000"
    while next_page:
        page = rebrickable_get(next_page)
        for item in page.get("results", []):
            if item.get("is_spare"):
                continue
            color = item.get("color") or {}
            part = item.get("part") or {}
            key = (part.get("part_num", ""), int(color.get("id") or 0))
            if not key[0]:
                continue
            entry = parts.setdefault(
                key,
                {
                    "part_num": key[0],
                    "part_name": part.get("name") or key[0],
                    "color_id": key[1],
                    "color_name": color.get("name") or "Unknown",
                    "quantity": 0,
                    "image_url": part.get("part_img_url") or "",
                    "item_type": "part",
                },
            )
            entry["quantity"] += int(item.get("quantity") or 0)
        next_page = page.get("next")
        if next_page:
            parsed = urllib.parse.urlparse(next_page)
            next_page = parsed.path.removeprefix("/api/v3/lego/")
            if parsed.query:
                next_page += f"?{parsed.query}"

    minifigs = {}
    try:
        figs_next = (
            f"sets/{urllib.parse.quote(set_num, safe='-')}/minifigs/?page_size=1000"
        )
        while figs_next:
            page = rebrickable_get(figs_next)
            for item in page.get("results", []):
                fig_num = item.get("set_num") or ""
                if not fig_num.startswith("fig-"):
                    continue
                try:
                    fig_quantity = int(item.get("quantity") or 0)
                except (TypeError, ValueError):
                    continue
                if fig_quantity <= 0:
                    continue
                minifigs[(fig_num, 0)] = {
                    "part_num": fig_num,
                    "part_name": item.get("set_name") or fig_num,
                    "color_id": 0,
                    "color_name": "Figurine",
                    "quantity": fig_quantity,
                    "image_url": item.get("set_img_url") or "",
                    "item_type": "minifig",
                }
            figs_next = page.get("next")
            if figs_next:
                parsed = urllib.parse.urlparse(figs_next)
                figs_next = parsed.path.removeprefix("/api/v3/lego/")
                if parsed.query:
                    figs_next += f"?{parsed.query}"
    except (RuntimeError, ValueError):
        pass

    for key, minifig in minifigs.items():
        parts.setdefault(key, minifig)
    return set_info, list(parts.values())


def fetch_minifig_parts_for_set(set_num):
    """Récupère la composition de chaque figurine d'un set (informatif uniquement)."""
    rows = []
    figs_next = f"sets/{urllib.parse.quote(set_num, safe='-')}/minifigs/?page_size=1000"
    seen_fig_nums = set()
    while figs_next:
        page = rebrickable_get(figs_next)
        for item in page.get("results", []):
            fig_num = item.get("set_num") or ""
            if not fig_num.startswith("fig-"):
                continue
            try:
                fig_quantity = int(item.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
            if fig_quantity <= 0 or fig_num in seen_fig_nums:
                continue
            seen_fig_nums.add(fig_num)
            try:
                parts_next = (
                    f"minifigs/{urllib.parse.quote(fig_num, safe='-')}"
                    "/parts/?page_size=1000"
                )
                fig_rows = {}
                while parts_next:
                    parts_page = rebrickable_get(parts_next)
                    for part_item in parts_page.get("results", []):
                        color = part_item.get("color") or {}
                        part = part_item.get("part") or {}
                        part_num = part.get("part_num") or ""
                        if not part_num:
                            continue
                        try:
                            color_id = int(color.get("id") or 0)
                        except (TypeError, ValueError):
                            color_id = 0
                        try:
                            quantity = int(part_item.get("quantity") or 0)
                        except (TypeError, ValueError):
                            quantity = 0
                        key = (part_num, color_id)
                        entry = fig_rows.get(key)
                        if entry is None:
                            fig_rows[key] = {
                                "fig_num": fig_num,
                                "part_num": part_num,
                                "part_name": part.get("name") or part_num,
                                "color_id": color_id,
                                "color_name": color.get("name") or "Unknown",
                                "quantity": quantity,
                                "image_url": part.get("part_img_url") or "",
                            }
                        else:
                            entry["quantity"] += quantity
                    parts_next = parts_page.get("next")
                    if parts_next:
                        parsed = urllib.parse.urlparse(parts_next)
                        parts_next = parsed.path.removeprefix("/api/v3/lego/")
                        if parsed.query:
                            parts_next += f"?{parsed.query}"
            except (RuntimeError, ValueError):
                continue
            rows.extend(
                row for row in fig_rows.values() if row["quantity"] > 0
            )
        figs_next = page.get("next")
        if figs_next:
            parsed = urllib.parse.urlparse(figs_next)
            figs_next = parsed.path.removeprefix("/api/v3/lego/")
            if parsed.query:
                figs_next += f"?{parsed.query}"
    return rows


def get_minifig_parts_map():
    """Composition des figurines, agrégée par (fig_num, part_num, color_id)."""
    with database() as connection:
        rows = connection.execute(
            """
            SELECT fig_num, part_num, part_name, color_id, color_name,
                   MAX(quantity) AS quantity, MAX(image_url) AS image_url
            FROM minifig_parts
            GROUP BY fig_num, part_num, color_id
            ORDER BY fig_num, color_name COLLATE NOCASE,
                     part_name COLLATE NOCASE
            """
        ).fetchall()
    mapping = {}
    for row in rows:
        mapping.setdefault(row["fig_num"], []).append(
            {
                "fig_num": row["fig_num"],
                "part_num": row["part_num"],
                "part_name": row["part_name"],
                "color_id": int(row["color_id"] or 0),
                "color_name": row["color_name"],
                "quantity": int(row["quantity"] or 0),
                "image_url": row["image_url"] or "",
            }
        )
    return mapping


def get_gathering_minifig_parts_map():
    with database() as connection:
        rows = connection.execute(
            """
            SELECT mp.id, mp.set_id, mp.fig_num, mp.part_num, mp.part_name,
                   mp.color_id, mp.color_name, mp.quantity * p.quantity AS quantity,
                   mp.missing_quantity,
                   mp.image_url
            FROM minifig_parts mp
            JOIN sets s ON s.id = mp.set_id
            JOIN set_parts p ON p.set_id = mp.set_id
                AND p.part_num = mp.fig_num AND p.item_type = 'minifig'
            WHERE s.in_gathering = 1
            ORDER BY mp.set_id, mp.fig_num, mp.color_name COLLATE NOCASE,
                     mp.part_name COLLATE NOCASE
            """
        ).fetchall()
    mapping = {}
    for row in rows:
        mapping.setdefault(row["set_id"], {}).setdefault(row["fig_num"], []).append(
            {
                "id": row["id"],
                "fig_num": row["fig_num"],
                "part_num": row["part_num"],
                "part_name": row["part_name"],
                "color_id": int(row["color_id"] or 0),
                "color_name": row["color_name"],
                "quantity": int(row["quantity"] or 0),
                "missing_quantity": int(row["missing_quantity"] or 0),
                "image_url": row["image_url"] or "",
            }
        )
    return mapping


def sync_minifig_components_from_parent(connection, part_id, previous_missing):
    parent = connection.execute(
        "SELECT set_id, part_num, item_type, missing_quantity FROM set_parts WHERE id = ?",
        (part_id,),
    ).fetchone()
    if not parent or parent["item_type"] != "minifig":
        return
    missing = parent["missing_quantity"]
    if missing == previous_missing:
        return
    connection.execute(
        """
        UPDATE minifig_parts
        SET missing_quantity = MAX(0, missing_quantity + quantity * ?)
        WHERE set_id = ? AND fig_num = ?
        """,
        (missing - previous_missing, parent["set_id"], parent["part_num"]),
    )


def sync_minifig_parent_from_components(connection, set_id, fig_num):
    connection.execute(
        """
        UPDATE set_parts
        SET missing_quantity = (
            SELECT MIN(set_parts.quantity, MAX(
                (mp.missing_quantity + mp.quantity - 1) / mp.quantity))
            FROM minifig_parts mp
            WHERE mp.set_id = set_parts.set_id AND mp.fig_num = set_parts.part_num
        )
        WHERE set_id = ? AND part_num = ? AND item_type = 'minifig'
          AND EXISTS (
              SELECT 1 FROM minifig_parts mp
              WHERE mp.set_id = set_parts.set_id AND mp.fig_num = set_parts.part_num
          )
        """,
        (set_id, fig_num),
    )


def replace_set_minifig_parts(
    connection, set_id, rows, all_parts_found=False, previous_figure_quantities=None
):
    previous_components = {
        (row["fig_num"], row["part_num"], row["color_id"]): row
        for row in connection.execute(
            """
            SELECT fig_num, part_num, color_id, quantity, missing_quantity
            FROM minifig_parts WHERE set_id = ?
            """,
            (set_id,),
        ).fetchall()
    }
    parents = {
        row["part_num"]: row
        for row in connection.execute(
            """
            SELECT part_num, quantity, missing_quantity FROM set_parts
            WHERE set_id = ? AND item_type = 'minifig'
            """,
            (set_id,),
        )
    }
    previous_figure_quantities = previous_figure_quantities or {
        fig_num: parent["quantity"] for fig_num, parent in parents.items()
    }
    components = []
    for row in rows:
        fig_num = row.get("fig_num") or ""
        part_num = row.get("part_num") or ""
        color_id = int(row.get("color_id") or 0)
        quantity = int(row.get("quantity") or 0)
        parent = parents.get(fig_num)
        figure_quantity = parent["quantity"] if parent else 1
        previous = previous_components.get((fig_num, part_num, color_id))
        if previous is not None:
            previous_total = previous["quantity"] * previous_figure_quantities.get(fig_num, 1)
            found = max(0, previous_total - previous["missing_quantity"])
            missing = max(0, quantity * figure_quantity - found)
        else:
            missing_figures = parent["missing_quantity"] if parent else (0 if all_parts_found else 1)
            missing = quantity * missing_figures
        components.append(
            {
                "set_id": set_id,
                "fig_num": fig_num,
                "part_num": part_num,
                "part_name": row.get("part_name") or part_num,
                "color_id": color_id,
                "color_name": row.get("color_name") or "Unknown",
                "quantity": quantity,
                "missing_quantity": missing,
                "image_url": row.get("image_url") or "",
            }
        )
    connection.execute("DELETE FROM minifig_parts WHERE set_id = ?", (set_id,))
    connection.executemany(
        """
        INSERT INTO minifig_parts
            (set_id, fig_num, part_num, part_name, color_id, color_name,
             quantity, missing_quantity, image_url)
        VALUES
            (:set_id, :fig_num, :part_num, :part_name, :color_id, :color_name,
             :quantity, :missing_quantity, :image_url)
        """,
        components,
    )
    for fig_num in {row.get("fig_num") or "" for row in rows}:
        sync_minifig_parent_from_components(connection, set_id, fig_num)


@app.get("/")
def index():
    destination = {
        "missing": "missing_page",
        "sets": "sets_page",
    }.get(request.form.get("return_to"), "pieces_page")
    return redirect(url_for(destination))


@app.get("/health")
def health():
    try:
        with database() as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error:
        app.logger.exception("Health check failed while accessing the database")
        return jsonify(status="unhealthy"), 503
    return jsonify(status="ok")


def get_owned_parts(connection):
    """Agrège toutes les pièces possédées, tous emplacements confondus.

    Le total possédé est toujours recalculé (jamais stocké) :
    total = vrac + pièces issues des sets en collection + pièces réservées
    (sets en préparation dont la pièce a été trouvée au moins en partie).
    """
    rows = connection.execute(
        """
        SELECT part_num, color_id,
               MAX(part_name) AS part_name,
               MAX(color_name) AS color_name,
               MAX(item_type) AS item_type,
               MAX(image_url) AS image_url,
               SUM(stock_qty) AS stock_qty,
               SUM(set_qty) AS set_qty,
               SUM(reserved_qty) AS reserved_qty
        FROM (
            SELECT sp.part_num, sp.color_id, sp.part_name, sp.color_name,
                   sp.item_type, sp.image_url,
                   sp.quantity AS stock_qty, 0 AS set_qty, 0 AS reserved_qty
            FROM stock_parts sp
            UNION ALL
            SELECT p.part_num, p.color_id, MAX(p.part_name), MAX(p.color_name),
                   MAX(p.item_type), MAX(p.image_url),
                   0, SUM(p.quantity - p.missing_quantity), 0
            FROM set_parts p JOIN sets s ON s.id = p.set_id
            WHERE s.in_collection = 1
            GROUP BY p.part_num, p.color_id
            UNION ALL
            SELECT p.part_num, p.color_id, MAX(p.part_name), MAX(p.color_name),
                   MAX(p.item_type), MAX(p.image_url),
                   0, 0, SUM(p.quantity - p.missing_quantity)
            FROM set_parts p JOIN sets s ON s.id = p.set_id
            WHERE s.in_gathering = 1 AND s.in_collection = 0
              AND p.missing_quantity < p.quantity
            GROUP BY p.part_num, p.color_id
        )
        GROUP BY part_num, color_id
        HAVING SUM(stock_qty) + SUM(set_qty) + SUM(reserved_qty) > 0
        ORDER BY color_name COLLATE NOCASE, part_name COLLATE NOCASE,
                 part_num, item_type
        """
    ).fetchall()

    reserved_set_nums = {}
    reserved_set_tones = {}
    for row in connection.execute(
        """
        SELECT p.part_num, p.color_id, s.set_num, s.id AS set_id
        FROM set_parts p JOIN sets s ON s.id = p.set_id
        WHERE s.in_gathering = 1 AND s.in_collection = 0
          AND p.missing_quantity < p.quantity
        ORDER BY s.set_num, s.id
        """
    ):
        key = (row["part_num"], int(row["color_id"]))
        reserved_set_nums.setdefault(key, []).append(row["set_num"])
        tones = reserved_set_tones.setdefault(key, [])
        tone = int(row["set_id"]) % 6
        if tone not in tones:
            tones.append(tone)

    collected_set_counts = {
        (row["part_num"], int(row["color_id"])): int(row["set_count"] or 0)
        for row in connection.execute(
            """
            SELECT p.part_num, p.color_id, COUNT(DISTINCT s.id) AS set_count
            FROM set_parts p JOIN sets s ON s.id = p.set_id
            WHERE s.in_collection = 1
              AND p.quantity > p.missing_quantity
            GROUP BY p.part_num, p.color_id
            """
        )
    }

    stock_ids = {
        (row["part_num"], int(row["color_id"])): row["id"]
        for row in connection.execute(
            "SELECT id, part_num, color_id FROM stock_parts"
        )
    }

    owned = {}
    for row in rows:
        key = (row["part_num"], int(row["color_id"] or 0))
        stock_qty = int(row["stock_qty"] or 0)
        set_qty = int(row["set_qty"] or 0)
        reserved_qty = int(row["reserved_qty"] or 0)
        total = stock_qty + set_qty + reserved_qty
        counter_count = sum(
            1 for quantity in (stock_qty, set_qty, reserved_qty) if quantity > 0
        )
        if counter_count == 1:
            if stock_qty > 0:
                origin = "stock"
            elif set_qty > 0:
                origin = "sets"
            else:
                origin = "reserved"
        else:
            origin = "mixed"

        badges = []
        if stock_qty > 0 and set_qty > 0:
            badges.append({"label": "Sets + vrac", "tone": "mixed"})
        elif stock_qty > 0:
            badges.append({"label": "En stock", "tone": "stock"})
        elif set_qty > 0:
            badges.append({"label": "Dans un set", "tone": "sets"})
        if reserved_qty > 0:
            set_nums = list(dict.fromkeys(reserved_set_nums.get(key, [])))
            label = "Réservé"
            if set_nums:
                label = f"Réservé · {', '.join(set_nums)}"
            tones = reserved_set_tones.get(key, [])
            badges.append(
                {
                    "label": label,
                    "tone": "reserved",
                    "set_tone": tones[0] if tones else None,
                }
            )

        owned[key] = {
            "part_num": row["part_num"],
            "color_id": int(row["color_id"] or 0),
            "part_name": row["part_name"],
            "color_name": row["color_name"],
            "item_type": row["item_type"] or "part",
            "image_url": row["image_url"] or "",
            "stock_qty": stock_qty,
            "set_qty": set_qty,
            "set_count": collected_set_counts.get(key, 0),
            "reserved_qty": reserved_qty,
            "reserved_set_count": len(
                dict.fromkeys(reserved_set_nums.get(key, []))
            ),
            "total": total,
            # Clé de compatibilité pour le rendu « ×{{ quantity }} ».
            "quantity": total,
            "origin": origin,
            "badges": badges,
            "stock_id": stock_ids.get(key),
        }
    return owned


def _stock_update_response(connection, part_num, color_id):
    """Réponse JSON d'une mise à jour du vrac : la carte d'inventaire re-rendue."""
    part = get_owned_parts(connection).get((part_num, int(color_id)))
    if part is None:
        return jsonify(
            {"removed": True, "html": "", "total": 0, "quantity": 0, "stock_id": None}
        )
    return jsonify(
        {
            "removed": False,
            "html": render_template(
                "_inventory_card.html",
                part=part,
                minifig_parts=get_minifig_parts_map(),
            ),
            "total": part["total"],
            "quantity": part["stock_qty"],
            "stock_id": part["stock_id"],
        }
    )


def get_piece_groups(
    search="",
    color_filter="",
    sort_by="color",
    missing_only=False,
    owned_only=False,
    gathering_only=False,
):
    where = ["s.in_gathering = 1"] if gathering_only else ["s.in_collection = ?"]
    params = [] if gathering_only else [int(owned_only)]
    if search:
        like = f"%{search}%"
        where.append(
            "(s.set_num LIKE ? OR s.title LIKE ? OR p.part_num LIKE ? "
            "OR p.part_name LIKE ? OR p.color_name LIKE ?)"
        )
        params.extend([like] * 5)
    if color_filter:
        where.append("p.color_name = ?")
        params.append(color_filter)
    copy_state = "in_gathering" if gathering_only else "in_collection"
    sql = """
        SELECT s.id AS set_id, s.set_num, s.title, s.set_image_url,
               s.theme_name, s.year, s.in_gathering,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num AND other.id <= s.id
                  AND other.{copy_state} = 1) AS copy_number,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num
                  AND other.{copy_state} = 1) AS copy_count,
               p.id AS part_id, p.part_num, p.part_name, p.color_id,
               p.color_name, p.quantity, p.missing_quantity, p.image_url, p.item_type
        FROM sets s JOIN set_parts p ON p.set_id = s.id
    """
    sql = sql.format(copy_state=copy_state)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.color_name COLLATE NOCASE, p.part_name COLLATE NOCASE, s.set_num"

    with database() as connection:
        rows = connection.execute(sql, params).fetchall()
        colors = [
            row["color_name"]
            for row in connection.execute(
                """
                SELECT DISTINCT p.color_name
                FROM sets s JOIN set_parts p ON p.set_id = s.id
                WHERE (? AND s.in_gathering = 1) OR (NOT ? AND s.in_collection = ?)
                ORDER BY p.color_name COLLATE NOCASE
                """,
                (int(gathering_only), int(gathering_only), int(owned_only)),
            ).fetchall()
        ]

    grouped_parts = {}
    for row in rows:
        key = (row["part_num"], row["color_id"])
        part = grouped_parts.setdefault(
            key,
            {
                "part_num": row["part_num"],
                "part_name": row["part_name"],
                "color_id": row["color_id"],
                "color_name": row["color_name"],
                "image_url": row["image_url"],
                "item_type": row["item_type"] or "part",
                "quantity": 0,
                "missing": 0,
                "sets": [],
            },
        )
        part["quantity"] += row["quantity"]
        part["missing"] += row["missing_quantity"]
        part["sets"].append(
            {
                "id": row["set_id"],
                "title": row["title"],
                "set_num": row["set_num"],
                "theme_name": row["theme_name"],
                "year": row["year"],
                "copy_number": row["copy_number"],
                "copy_count": row["copy_count"],
                "quantity": row["quantity"],
                "missing": row["missing_quantity"],
                "part_id": row["part_id"],
            }
        )

    sort_keys = {
        "color": lambda item: (
            item["color_name"] == "Figurine",
            item["color_name"].casefold(),
            item["part_name"].casefold(),
        ),
        "name": lambda item: (item["part_name"].casefold(), item["color_name"].casefold()),
        "missing": lambda item: (-item["missing"], item["color_name"].casefold(), item["part_name"].casefold()),
        "quantity": lambda item: (-item["quantity"], item["color_name"].casefold(), item["part_name"].casefold()),
    }
    with database() as connection:
        stock_map = {
            (row["part_num"], int(row["color_id"] or 0)): int(row["quantity"])
            for row in connection.execute(
                "SELECT part_num, color_id, quantity FROM stock_parts"
            ).fetchall()
        }
    for key, part in grouped_parts.items():
        part["stock_qty"] = stock_map.get((key[0], int(key[1] or 0)), 0)
    parts = list(grouped_parts.values())
    if missing_only:
        parts = [part for part in parts if part["missing"] > 0]
    parts.sort(key=sort_keys.get(sort_by, sort_keys["color"]))

    color_groups = {}
    for part in parts:
        color_groups.setdefault(part["color_name"], []).append(part)
    groups = [
        {
            "name": color_name,
            "hex": lego_color_hex(color_name),
            "parts": color_parts,
            "missing": sum(part["missing"] for part in color_parts),
            "quantity": sum(part["quantity"] for part in color_parts),
        }
        for color_name, color_parts in color_groups.items()
    ]
    return groups, colors, parts


def split_color_groups(groups):
    columns = [[], []]
    heights = [0, 0]
    for group in groups:
        column_index = 0 if heights[0] <= heights[1] else 1
        columns[column_index].append(group)
        heights[column_index] += len(group["parts"]) + 2
    return columns


@app.get("/pieces")
def pieces_page():
    search = request.args.get("q", "").strip()
    color_filter = request.args.get("color", "").strip()
    sort_by = request.args.get("sort", "color")
    groups, colors, parts = get_piece_groups(
        search, color_filter, sort_by, gathering_only=True
    )
    copy_state = "in_gathering"
    with database() as connection:
        sets_to_assemble = [
            dict(row)
            for row in connection.execute(
                """
                SELECT s.id, s.set_num, s.title, s.set_image_url, s.year, s.theme_name,
                       s.in_collection,
                       (SELECT COUNT(*) FROM sets other
                        WHERE other.set_num = s.set_num AND other.id <= s.id
                          AND other.{copy_state} = 1) AS copy_number,
                       (SELECT COUNT(*) FROM sets other
                        WHERE other.set_num = s.set_num
                          AND other.{copy_state} = 1) AS copy_count,
                       COALESCE(SUM(p.quantity), 0) AS total,
                       COALESCE(SUM(p.missing_quantity), 0) AS missing,
                       COUNT(p.id) AS part_count
                FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
                WHERE s.in_gathering = 1
                GROUP BY s.id
                ORDER BY s.created_at DESC, s.set_num
                """.format(copy_state=copy_state)
            ).fetchall()
        ]
    return render_template(
        "pieces.html",
        groups=groups,
        group_columns=split_color_groups(groups),
        colors=colors,
        parts=parts,
        search=search,
        color_filter=color_filter,
        sort_by=sort_by,
        sets_to_assemble=sets_to_assemble,
        has_api_key=bool(os.environ.get("REBRICKABLE_API_KEY", "").strip()),
        minifig_parts_by_set=get_gathering_minifig_parts_map(),
    )


@app.get("/sets")
def sets_page():
    search = request.args.get("q", "").strip()
    copy_state = "in_collection"
    params = []
    sql = """
        SELECT s.id AS set_id, s.set_num, s.title, s.set_image_url, s.year,
               s.theme_name, s.in_gathering,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num AND other.id <= s.id
                  AND other.{copy_state} = 1) AS copy_number,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num
                  AND other.{copy_state} = 1) AS copy_count,
               p.id AS part_id, p.part_num, p.part_name, p.color_id,
               p.color_name, p.quantity, p.missing_quantity, p.image_url
        FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
        WHERE s.in_collection = 1
    """.format(copy_state=copy_state)
    if search:
        sql += " AND (s.set_num LIKE ? OR s.title LIKE ?)"
        params.extend([f"%{search}%"] * 2)
    sql += " ORDER BY s.created_at DESC, s.set_num, p.part_name, p.color_name"
    with database() as connection:
        rows = connection.execute(sql, params).fetchall()
    sets = {}
    for row in rows:
        item = sets.setdefault(
            row["set_id"],
            {
                "id": row["set_id"],
                "set_num": row["set_num"],
                "copy_number": row["copy_number"],
                "copy_count": row["copy_count"],
                "title": row["title"],
                "set_image_url": row["set_image_url"],
                "year": row["year"],
                "theme_name": row["theme_name"],
                "parts": [],
                "total": 0,
                "missing": 0,
            },
        )
        if row["part_id"] is not None:
            part = dict(row)
            item["parts"].append(part)
            item["total"] += part["quantity"]
            item["missing"] += part["missing_quantity"]
    theme_groups = {}
    for set_item in sets.values():
        theme_groups.setdefault(set_item["theme_name"], []).append(set_item)
    return render_template(
        "sets.html",
        theme_groups=[
            {"name": name, "sets": theme_sets}
            for name, theme_sets in sorted(
                theme_groups.items(),
                key=lambda item: (
                    item[0] == "Thème non renseigné",
                    item[0].casefold(),
                ),
            )
        ],
        set_count=len(sets),
        search=search,
        has_api_key=bool(os.environ.get("REBRICKABLE_API_KEY", "").strip()),
        minifig_parts=get_minifig_parts_map(),
    )


@app.get("/inventaire")
def inventory_page():
    search = request.args.get("q", "").strip()
    color_filter = request.args.get("color", "").strip()
    origin_filter = request.args.get("origin", "all").strip()
    if origin_filter not in {"all", "stock", "sets", "reserved", "mixed"}:
        origin_filter = "all"

    with database() as connection:
        owned = get_owned_parts(connection)

        matched_keys = set()
        if search:
            like = f"%{search}%"
            matched_keys = {
                (row["part_num"], int(row["color_id"] or 0))
                for row in connection.execute(
                    """
                    SELECT DISTINCT p.part_num, p.color_id
                    FROM sets s JOIN set_parts p ON p.set_id = s.id
                    WHERE s.set_num LIKE ? OR s.title LIKE ?
                    """,
                    (like, like),
                ).fetchall()
            }

        stock_color_options = [
            {"color_id": color_id, "color_name": color_name}
            for color_id, color_name in sorted(
                {
                    int(row["color_id"]): row["color_name"]
                    for row in connection.execute(
                        """
                        SELECT color_id, color_name FROM stock_parts
                        UNION
                        SELECT color_id, color_name FROM set_parts
                        """
                    ).fetchall()
                }.items(),
                key=lambda item: (item[1].casefold(), item[0]),
            )
        ]

    def matches_origin(part):
        if origin_filter == "stock":
            return part["stock_qty"] > 0
        if origin_filter == "sets":
            return part["set_qty"] > 0
        if origin_filter == "reserved":
            return part["reserved_qty"] > 0
        if origin_filter == "mixed":
            return (
                sum(
                    1
                    for quantity in (
                        part["stock_qty"],
                        part["set_qty"],
                        part["reserved_qty"],
                    )
                    if quantity > 0
                )
                >= 2
            )
        return True

    needle = search.casefold()
    parts = []
    for part in owned.values():
        if not matches_origin(part):
            continue
        if needle:
            haystack = " ".join(
                (part["part_num"], part["part_name"], part["color_name"])
            ).casefold()
            if needle not in haystack and (part["part_num"], part["color_id"]) not in matched_keys:
                continue
        if color_filter and part["color_name"] != color_filter:
            continue
        parts.append(part)

    color_groups = {}
    for part in parts:
        group = color_groups.setdefault(
            part["color_name"], {"name": part["color_name"], "parts": [], "quantity": 0}
        )
        group["parts"].append(part)
        group["quantity"] += part["total"]

    groups = list(color_groups.values())
    groups.sort(key=lambda group: group["name"] == "Figurine")

    colors = sorted(
        {part["color_name"] for part in owned.values()},
        key=lambda name: name.casefold(),
    )

    return render_template(
        "inventory.html",
        groups=groups,
        colors=colors,
        color_filter=color_filter,
        search=search,
        origin_filter=origin_filter,
        total_quantity=sum(part["total"] for part in parts),
        stock_quantity=sum(part["stock_qty"] for part in parts),
        set_quantity=sum(part["set_qty"] for part in parts),
        reserved_quantity=sum(part["reserved_qty"] for part in parts),
        part_count=len(parts),
        stock_color_options=stock_color_options,
        minifig_parts=get_minifig_parts_map(),
    )


@app.post("/stock")
def add_stock_part():
    part_num = request.form.get("part_num", "").strip()
    part_name = request.form.get("part_name", "").strip() or part_num
    color_name = request.form.get("color_name", "").strip() or "Unknown"
    item_type = request.form.get("item_type", "").strip().lower() or "part"
    if item_type not in {"part", "minifig"}:
        item_type = "part"
    image_url = request.form.get("image_url", "").strip()
    raw_color_id = request.form.get("color_id", "").strip()
    try:
        color_id = int(raw_color_id) if raw_color_id else 0
    except (TypeError, ValueError):
        flash("Couleur invalide pour cette pièce du vrac.", "error")
        return redirect(url_for("inventory_page"))
    if color_id < 0:
        flash("Couleur invalide pour cette pièce du vrac.", "error")
        return redirect(url_for("inventory_page"))
    try:
        quantity = int(request.form.get("quantity", "0"))
    except (TypeError, ValueError):
        quantity = 0
    if not part_num or quantity <= 0:
        flash("Indiquez une référence et une quantité valide pour le vrac.", "error")
        return redirect(url_for("inventory_page"))
    with database() as connection:
        connection.execute(
            """
            INSERT INTO stock_parts
                (part_num, color_id, part_name, color_name, item_type, image_url, quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(part_num, color_id) DO UPDATE SET
                quantity = stock_parts.quantity + excluded.quantity,
                part_name = excluded.part_name,
                color_name = excluded.color_name,
                item_type = excluded.item_type,
                image_url = CASE WHEN excluded.image_url != ''
                                 THEN excluded.image_url
                                 ELSE stock_parts.image_url END
            """,
            (part_num, color_id, part_name, color_name, item_type, image_url, quantity),
        )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        with database() as connection:
            return _stock_update_response(connection, part_num, color_id)
    flash(f"{quantity} × {part_name} ajouté(s) au vrac.", "success")
    return redirect(url_for("inventory_page"))


@app.post("/stock/<int:stock_id>/adjust")
def adjust_stock_part(stock_id):
    with database() as connection:
        row = connection.execute(
            """
            SELECT id, part_num, color_id, part_name, quantity
            FROM stock_parts WHERE id = ?
            """,
            (stock_id,),
        ).fetchone()
    if row is None:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Cette entrée du vrac n'existe plus."}), 404
        flash("Cette entrée du vrac n'existe plus.", "error")
        return redirect(url_for("inventory_page"))
    form_quantity = request.form.get("quantity")
    if form_quantity is not None and form_quantity.strip() != "":
        try:
            quantity = int(form_quantity)
            if quantity < 0:
                raise ValueError
        except (TypeError, ValueError):
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Quantité invalide."}), 400
            flash("Quantité invalide.", "error")
            return redirect(url_for("inventory_page"))
    else:
        try:
            change = int(request.form.get("change", "0"))
        except (TypeError, ValueError):
            change = 0
        quantity = row["quantity"] + change
    if quantity <= 0:
        with database() as connection:
            connection.execute("DELETE FROM stock_parts WHERE id = ?", (stock_id,))
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return _stock_update_response(
                    connection, row["part_num"], row["color_id"]
                )
        flash(f"{row['part_name']} retiré du vrac.", "success")
        return redirect(url_for("inventory_page"))
    with database() as connection:
        connection.execute(
            "UPDATE stock_parts SET quantity = ? WHERE id = ?",
            (quantity, stock_id),
        )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        with database() as connection:
            return _stock_update_response(
                connection, row["part_num"], row["color_id"]
            )
    flash(f"{row['part_name']} : {quantity} dans le vrac.", "success")
    return redirect(url_for("inventory_page"))


@app.post("/stock/<int:stock_id>/delete")
def delete_stock_part(stock_id):
    with database() as connection:
        row = connection.execute(
            "SELECT part_name, part_num, color_id FROM stock_parts WHERE id = ?",
            (stock_id,),
        ).fetchone()
        if row is None:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Cette entrée du vrac n'existe plus."}), 404
            flash("Cette entrée du vrac n'existe plus.", "error")
            return redirect(url_for("inventory_page"))
        connection.execute("DELETE FROM stock_parts WHERE id = ?", (stock_id,))
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return _stock_update_response(connection, row["part_num"], row["color_id"])
    flash(f"{row['part_name']} retiré du vrac.", "success")
    return redirect(url_for("inventory_page"))


@app.post("/pieces/take-stock")
def take_stock_for_part():
    part_num = request.form.get("part_num", "")
    try:
        color_id = int(request.form.get("color_id", ""))
    except ValueError:
        flash("Pièce invalide.", "error")
        return redirect(url_for("pieces_page"))
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    updates = []
    taken = 0
    available = 0
    with database() as connection:
        stock = connection.execute(
            "SELECT id, quantity FROM stock_parts WHERE part_num = ? AND color_id = ?",
            (part_num, color_id),
        ).fetchone()
        if stock is not None and stock["quantity"] > 0:
            rows = connection.execute(
                """
                SELECT sp.id, sp.missing_quantity, sp.item_type
                FROM set_parts sp JOIN sets s ON s.id = sp.set_id
                WHERE sp.part_num = ? AND sp.color_id = ? AND s.in_gathering = 1
                  AND sp.missing_quantity > 0
                ORDER BY s.created_at, s.id
                """,
                (part_num, color_id),
            ).fetchall()
            available = stock["quantity"]
            for row in rows:
                take = min(row["missing_quantity"], available)
                if take <= 0:
                    break
                connection.execute(
                    "UPDATE set_parts SET missing_quantity = ? WHERE id = ?",
                    (row["missing_quantity"] - take, row["id"]),
                )
                sync_minifig_components_from_parent(
                    connection, row["id"], row["missing_quantity"]
                )
                updates.append(
                    {
                        "part_id": row["id"],
                        "missing": row["missing_quantity"] - take,
                        "item_type": row["item_type"],
                    }
                )
                available -= take
                taken += take
            if taken:
                if available <= 0:
                    connection.execute(
                        "DELETE FROM stock_parts WHERE id = ?", (stock["id"],)
                    )
                else:
                    connection.execute(
                        "UPDATE stock_parts SET quantity = ? WHERE id = ?",
                        (available, stock["id"]),
                    )
    if ajax:
        if not taken:
            return jsonify({"error": "Aucune pièce du vrac à utiliser pour cette référence."}), 400
        return jsonify({"taken": taken, "stock_qty": available, "updates": updates})
    if taken:
        flash(f"{taken} pièce{'s' if taken > 1 else ''} prise{'s' if taken > 1 else ''} dans le vrac.", "success")
    else:
        flash("Aucune pièce du vrac à utiliser pour cette référence.", "error")
    return redirect(url_for("pieces_page"))


@app.post("/sets/<int:set_id>/take-stock")
def take_stock_for_set(set_id):
    return_to = request.form.get("return_to", "")
    with database() as connection:
        rows = connection.execute(
            """
            SELECT sp.id AS sp_id, sp.missing_quantity,
                   st.id AS stock_id, st.quantity AS stock_quantity
            FROM set_parts sp
            JOIN sets s ON s.id = sp.set_id
            JOIN stock_parts st
              ON st.part_num = sp.part_num AND st.color_id = sp.color_id
            WHERE sp.set_id = ? AND s.in_gathering = 1
              AND sp.missing_quantity > 0 AND st.quantity > 0
            """,
            (set_id,),
        ).fetchall()
        taken = 0
        for row in rows:
            take = min(row["missing_quantity"], row["stock_quantity"])
            if take <= 0:
                continue
            taken += take
            connection.execute(
                "UPDATE set_parts SET missing_quantity = ? WHERE id = ?",
                (row["missing_quantity"] - take, row["sp_id"]),
            )
            sync_minifig_components_from_parent(
                connection, row["sp_id"], row["missing_quantity"]
            )
            remaining = row["stock_quantity"] - take
            if remaining <= 0:
                connection.execute(
                    "DELETE FROM stock_parts WHERE id = ?", (row["stock_id"],)
                )
            else:
                connection.execute(
                    "UPDATE stock_parts SET quantity = ? WHERE id = ?",
                    (remaining, row["stock_id"]),
                )
    if taken > 0:
        flash(
            f"{taken} pièce{'s' if taken > 1 else ''} "
            f"prise{'s' if taken > 1 else ''} "
            "dans le vrac.",
            "success",
        )
    else:
        flash(
            "Aucune pièce du vrac ne correspond aux pièces manquantes de ce set.",
            "error",
        )
    if return_to == "verify":
        with database() as connection:
            set_row = connection.execute(
                "SELECT set_num FROM sets WHERE id = ?", (set_id,)
            ).fetchone()
        if set_row is not None and set_row["set_num"]:
            return redirect(url_for("verify_set_page", set_num=set_row["set_num"]))
        return redirect(url_for("inventory_page"))
    if return_to == "pieces":
        return redirect(url_for("pieces_page"))
    return redirect(url_for("inventory_page"))


@app.get("/inventaire/verifier")
def verify_set_page():
    raw_set_num = request.args.get("set_num", "").strip()
    context = {
        "set_num": raw_set_num,
        "rows": [],
        "summary": None,
        "error": None,
        "existing_set_id": None,
        "has_api_key": bool(os.environ.get("REBRICKABLE_API_KEY", "").strip()),
        "set_info": None,
        "checked": False,
        "minifig_parts": get_minifig_parts_map(),
    }
    if not raw_set_num:
        return render_template("verify_set.html", **context)

    set_num = raw_set_num
    if "-" not in set_num:
        set_num = f"{set_num}-1"
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", set_num):
        context["error"] = f"Numéro de set invalide : {raw_set_num}."
        return render_template("verify_set.html", **context)

    context["set_num"] = set_num
    if not context["has_api_key"]:
        context["error"] = "Configurez REBRICKABLE_API_KEY pour vérifier un set."
        return render_template("verify_set.html", **context)

    try:
        set_info, api_parts = fetch_set_inventory(set_num)
    except (RuntimeError, ValueError) as error:
        context["error"] = str(error)
        return render_template("verify_set.html", **context)

    with database() as connection:
        owned = get_owned_parts(connection)
        stock = {key: part["stock_qty"] for key, part in owned.items()}
        in_sets = {
            key: part["set_qty"] + part["reserved_qty"]
            for key, part in owned.items()
        }
        existing_row = connection.execute(
            """
            SELECT id FROM sets
            WHERE set_num = ? AND in_gathering = 1
            ORDER BY id LIMIT 1
            """,
            (set_num,),
        ).fetchone()

    rows = []
    for part in api_parts:
        needed = int(part.get("quantity") or 0)
        if needed <= 0:
            continue
        key = (str(part.get("part_num") or ""), int(part.get("color_id") or 0))
        stock_qty = stock.get(key, 0)
        sets_qty = in_sets.get(key, 0)
        take = min(needed, stock_qty)
        from_sets = min(sets_qty, needed - take)
        to_buy = max(0, needed - stock_qty - sets_qty)
        rows.append(
            {
                "part_num": part.get("part_num") or "",
                "part_name": part.get("part_name") or part.get("part_num") or "",
                "color_id": key[1],
                "color_name": part.get("color_name") or "Unknown",
                "item_type": part.get("item_type") or "part",
                "image_url": part.get("image_url") or "",
                "needed": needed,
                "stock": stock_qty,
                "in_sets": from_sets,
                "take": take,
                "to_buy": to_buy,
            }
        )
    rows.sort(
        key=lambda row: (row["color_name"].casefold(), row["part_name"].casefold())
    )

    summary = {
        "needed": sum(row["needed"] for row in rows),
        "from_stock": sum(row["take"] for row in rows),
        "from_sets": sum(row["in_sets"] for row in rows),
        "to_buy": sum(row["to_buy"] for row in rows),
    }
    summary["complete"] = summary["to_buy"] == 0

    context.update(
        rows=rows,
        summary=summary,
        set_info=set_info,
        existing_set_id=existing_row["id"] if existing_row else None,
        checked=True,
    )
    return render_template("verify_set.html", **context)


@app.post("/sets/<int:set_id>/refresh-image")
def refresh_set_image(set_id):
    with database() as connection:
        set_row = connection.execute(
            "SELECT set_num FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    if set_row is None:
        flash("Ce set n'existe plus.", "error")
        return redirect(url_for("sets_page"))
    try:
        set_info = fetch_set_info(set_row["set_num"])
    except (RuntimeError, ValueError) as error:
        flash(str(error), "error")
        return redirect(url_for("sets_page"))
    image_url = set_info.get("set_img_url") or ""
    if not image_url:
        flash(f"Rebrickable ne fournit pas d'image pour le set {set_row['set_num']}.", "error")
        return redirect(url_for("sets_page"))
    with database() as connection:
        connection.execute(
            "UPDATE sets SET set_image_url = ? WHERE id = ?",
            (image_url, set_id),
        )
    flash("Image du set récupérée depuis Rebrickable.", "success")
    return redirect(url_for("sets_page"))


@app.post("/sets/<int:set_id>/refresh-info")
def refresh_set_info(set_id):
    with database() as connection:
        set_row = connection.execute(
            "SELECT set_num FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    if set_row is None:
        flash("Ce set n'existe plus.", "error")
        return redirect(url_for("sets_page"))
    try:
        set_info = fetch_set_info(set_row["set_num"])
    except (RuntimeError, ValueError) as error:
        flash(str(error), "error")
        return redirect(url_for("sets_page"))
    year = set_info.get("year")
    if not isinstance(year, int):
        flash(f"Rebrickable ne fournit pas d'année pour le set {set_row['set_num']}.", "error")
        return redirect(url_for("sets_page"))
    with database() as connection:
        connection.execute("UPDATE sets SET year = ? WHERE id = ?", (year, set_id))
    flash(f"Année de sortie ({year}) récupérée depuis Rebrickable.", "success")
    return redirect(url_for("sets_page"))


@app.post("/sets/<int:set_id>/refresh-theme")
def refresh_set_theme(set_id):
    with database() as connection:
        set_row = connection.execute(
            "SELECT set_num FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    if set_row is None:
        flash("Ce set n'existe plus.", "error")
        return redirect(url_for("sets_page"))
    try:
        set_info = fetch_set_info(set_row["set_num"])
        theme_id = set_info.get("theme_id")
        if not theme_id:
            flash("Rebrickable ne fournit pas de thème pour ce set.", "error")
            return redirect(url_for("sets_page"))
        theme_name = fetch_theme_name(theme_id)
    except (RuntimeError, ValueError) as error:
        flash(str(error), "error")
        return redirect(url_for("sets_page"))
    with database() as connection:
        connection.execute(
            "UPDATE sets SET theme_name = ? WHERE id = ?",
            (theme_name, set_id),
        )
    flash(f"Thème « {theme_name} » récupéré depuis Rebrickable.", "success")
    return redirect(url_for("sets_page"))


@app.post("/sets/<int:set_id>/refresh-inventory")
def refresh_set_inventory(set_id):
    destination = {
        "sets": "sets_page",
    }.get(request.form.get("return_to"), "pieces_page")
    if not os.environ.get("REBRICKABLE_API_KEY", "").strip():
        flash("Ajoute une clé API Rebrickable pour actualiser l'inventaire.", "error")
        return redirect(url_for(destination))
    with database() as connection:
        set_row = connection.execute(
            "SELECT set_num, all_parts_found FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    if set_row is None:
        flash("Ce set n'existe plus.", "error")
        return redirect(url_for(destination))
    try:
        _, parts = fetch_set_inventory(set_row["set_num"])
    except (RuntimeError, ValueError) as error:
        flash(str(error), "error")
        return redirect(url_for(destination))

    try:
        minifig_rows = fetch_minifig_parts_for_set(set_row["set_num"])
    except (RuntimeError, ValueError):
        minifig_rows = None

    with database() as connection:
        previous_figure_quantities = {
            row["part_num"]: row["quantity"]
            for row in connection.execute(
                """
                SELECT part_num, quantity FROM set_parts
                WHERE set_id = ? AND item_type = 'minifig'
                """,
                (set_id,),
            ).fetchall()
        }
        previous_missing = {
            (row["part_num"], row["color_id"]): row["missing_quantity"]
            for row in connection.execute(
                "SELECT part_num, color_id, missing_quantity FROM set_parts WHERE set_id = ?",
                (set_id,),
            ).fetchall()
        }
        merged = {}
        for part in parts:
            quantity = int(part.get("quantity") or 0)
            key = (str(part.get("part_num") or ""), int(part.get("color_id") or 0))
            if not key[0] or quantity <= 0:
                continue
            if key in merged:
                merged[key]["quantity"] += quantity
                continue
            merged[key] = {
                "set_id": set_id,
                "part_num": key[0],
                "part_name": part.get("part_name") or key[0],
                "color_id": key[1],
                "color_name": part.get("color_name") or "Unknown",
                "quantity": quantity,
                "image_url": part.get("image_url") or "",
                "item_type": part.get("item_type", "part"),
            }
        for item in merged.values():
            key = (item["part_num"], item["color_id"])
            previous = previous_missing.get(key)
            if previous is None:
                item["missing_quantity"] = (
                    0 if set_row["all_parts_found"] else item["quantity"]
                )
            else:
                item["missing_quantity"] = min(previous, item["quantity"])
        if not merged:
            flash(
                "Inventaire introuvable : aucune pièce n'a été renvoyée par Rebrickable.",
                "error",
            )
            return redirect(url_for(destination))
        connection.execute("DELETE FROM set_parts WHERE set_id = ?", (set_id,))
        connection.executemany(
            """
            INSERT INTO set_parts
                (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity, image_url, item_type)
            VALUES
                (:set_id, :part_num, :part_name, :color_id, :color_name, :quantity, :missing_quantity, :image_url, :item_type)
            """,
            list(merged.values()),
        )
        if minifig_rows is not None:
            replace_set_minifig_parts(
                connection,
                set_id,
                minifig_rows,
                all_parts_found=bool(set_row["all_parts_found"]),
                previous_figure_quantities=previous_figure_quantities,
            )
    count = len(merged)
    flash(
        f"Inventaire actualisé : {count} référence{'s' if count != 1 else ''}.",
        "success",
    )
    return redirect(url_for(destination))


@app.get("/manquantes")
def missing_page():
    search = request.args.get("q", "").strip()
    color_filter = request.args.get("color", "").strip()
    sort_by = request.args.get("sort", "color")
    groups, colors, parts = get_piece_groups(
        search, color_filter, sort_by, missing_only=True, owned_only=True
    )
    return render_template(
        "missing.html",
        groups=groups,
        group_columns=split_color_groups(groups),
        colors=colors,
        parts=parts,
        search=search,
        color_filter=color_filter,
        sort_by=sort_by,
        minifig_parts=get_minifig_parts_map(),
    )


@app.post("/sets")
def add_set():
    add_to_collection = request.form.get("return_to") == "sets"
    all_parts_found = add_to_collection and request.form.get("all_parts_found") == "1"
    destination = "sets_page" if add_to_collection else "pieces_page"
    raw_number = request.form.get("set_num", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", raw_number):
        flash("Entrez une référence de set valide, par exemple 10312 ou 10312-1.", "error")
        return redirect(url_for(destination))
    set_num = raw_number if "-" in raw_number else f"{raw_number}-1"
    title = request.form.get("title", "").strip()
    theme_name = request.form.get("theme_name", "").strip() or "Thème non renseigné"
    set_image_url = ""
    year = None
    parts = []
    theme_warning = ""
    if os.environ.get("REBRICKABLE_API_KEY", "").strip():
        try:
            set_info, parts = fetch_set_inventory(set_num)
            title = set_info.get("name") or title or f"Set {set_num}"
            set_image_url = set_info.get("set_img_url") or ""
            year = set_info.get("year")
            if set_info.get("theme_id"):
                try:
                    theme_name = fetch_theme_name(set_info["theme_id"])
                except (RuntimeError, ValueError) as error:
                    theme_name = f"Thème {set_info['theme_id']}"
                    theme_warning = (
                        f"Le thème n'a pas pu être récupéré depuis Rebrickable : {error}"
                    )
        except (RuntimeError, ValueError) as error:
            flash(str(error), "error")
            return redirect(url_for(destination))
    else:
        title = title or f"Set {set_num}"

    minifig_rows = []
    if os.environ.get("REBRICKABLE_API_KEY", "").strip():
        try:
            minifig_rows = fetch_minifig_parts_for_set(set_num)
        except (RuntimeError, ValueError):
            minifig_rows = []

    with database() as connection:
        cursor = connection.execute(
            """
            INSERT INTO sets
                (set_num, title, set_image_url, theme_name, year, in_collection, in_gathering, all_parts_found)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                set_num,
                title,
                set_image_url,
                theme_name,
                year,
                int(add_to_collection),
                int(not add_to_collection),
                int(all_parts_found),
            ),
        )
        set_id = cursor.lastrowid
        imported_parts = [
            dict(
                part,
                set_id=set_id,
                missing_quantity=0 if all_parts_found else part["quantity"],
                item_type=part.get("item_type", "part"),
            )
            for part in parts
        ]
        connection.executemany(
            """
            INSERT INTO set_parts
                (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity, image_url, item_type)
            VALUES
                (:set_id, :part_num, :part_name, :color_id, :color_name, :quantity, :missing_quantity, :image_url, :item_type)
            """,
            imported_parts,
        )
        if minifig_rows:
            replace_set_minifig_parts(
                connection,
                set_id,
                minifig_rows,
                all_parts_found=all_parts_found,
            )

    if parts:
        message = f"{title} ajouté avec {len(parts)} références de pièces importées."
        if all_parts_found:
            message += " Toutes les pièces sont marquées comme trouvées."
        flash(message, "success")
    elif os.environ.get("REBRICKABLE_API_KEY", "").strip():
        flash(f"{title} ajouté. Aucun élément n'a été retourné par Rebrickable.", "success")
    else:
        flash(
            f"{title} ajouté. Ajoutez ses pièces manuellement"
            + ("" if add_to_collection else ", ou configurez Rebrickable pour les importer automatiquement")
            + ".",
            "success",
        )
    if theme_warning:
        flash(theme_warning, "error")
    return redirect(url_for(destination))


@app.post("/sets/<int:set_id>/collect")
def collect_set(set_id):
    with database() as connection:
        set_row = connection.execute(
            """
            SELECT s.in_collection, COUNT(p.id) AS part_count,
                   COALESCE(SUM(p.missing_quantity), 0) AS missing
            FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
            WHERE s.id = ?
            GROUP BY s.id
            """,
            (set_id,),
        ).fetchone()
        if not set_row or not set_row["part_count"]:
            flash("Ajoutez d'abord les pièces du set avant de le valider.", "error")
            return redirect(url_for("pieces_page"))
        cursor = connection.execute(
            """
            UPDATE sets
            SET in_collection = 1,
                in_gathering = CASE WHEN ? = 0 THEN 0 ELSE in_gathering END
            WHERE id = ? AND in_collection = 0
            """,
            (set_row["missing"], set_id),
        )
    if cursor.rowcount:
        flash(
            "Set ajouté à Mes sets."
            + (" Toutes ses pièces sont déjà trouvées ; il est retiré de À réunir." if not set_row["missing"] else ""),
            "success",
        )
    else:
        flash("Ce set n'existe plus ou figure déjà dans Mes sets.", "error")
    return redirect(url_for("pieces_page"))


@app.post("/sets/<int:set_id>/gathering")
def update_set_gathering(set_id):
    gathering = request.form.get("in_gathering")
    destination = "pieces_page" if request.form.get("return_to") == "pieces" else "sets_page"
    if gathering not in {"0", "1"}:
        flash("État de recherche invalide.", "error")
        return redirect(url_for(destination))
    with database() as connection:
        cursor = connection.execute(
            """
            UPDATE sets
            SET in_gathering = ?,
                all_parts_found = CASE WHEN ? = 1 THEN 0 ELSE all_parts_found END
            WHERE id = ?
            """,
            (int(gathering), int(gathering), set_id),
        )
    if cursor.rowcount:
        message = (
            "Les pièces de ce set sont ajoutées à À réunir."
            if gathering == "1"
            else "Les pièces de ce set sont retirées de À réunir."
        )
        flash(message, "success")
    else:
        flash("Ce set n'existe plus.", "error")
    return redirect(url_for(destination))


@app.post("/sets/<int:set_id>/duplicate")
def duplicate_set(set_id):
    destination = request.form.get("return_to")
    if destination not in {"pieces", "sets"}:
        flash("Destination de l'exemplaire invalide.", "error")
        return redirect(url_for("pieces_page"))

    copy_state = "in_gathering" if destination == "pieces" else "in_collection"
    with database() as connection:
        source = connection.execute(
            f"""
            SELECT set_num, title, set_image_url, theme_name, year
            FROM sets WHERE id = ? AND {copy_state} = 1
            """,
            (set_id,),
        ).fetchone()
        if source is None:
            flash("Ce set n'existe plus dans cette liste.", "error")
            return redirect(url_for("pieces_page" if destination == "pieces" else "sets_page"))

        cursor = connection.execute(
            """
            INSERT INTO sets
                (set_num, title, set_image_url, theme_name, year,
                 in_collection, in_gathering, all_parts_found)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                source["set_num"],
                source["title"],
                source["set_image_url"],
                source["theme_name"],
                source["year"],
                int(destination == "sets"),
                int(destination == "pieces"),
            ),
        )
        new_set_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO set_parts
                (set_id, part_num, part_name, color_id, color_name,
                 quantity, missing_quantity, image_url, item_type)
            SELECT ?, part_num, part_name, color_id, color_name,
                   quantity, quantity, image_url, item_type
            FROM set_parts WHERE set_id = ?
            """,
            (new_set_id, set_id),
        )
        connection.execute(
            """
            INSERT INTO minifig_parts
                (set_id, fig_num, part_num, part_name, color_id, color_name,
                 quantity, missing_quantity, image_url)
            SELECT ?, mp.fig_num, mp.part_num, mp.part_name, mp.color_id, mp.color_name,
                   mp.quantity, mp.quantity * COALESCE(p.quantity, 1), mp.image_url
            FROM minifig_parts mp
            LEFT JOIN set_parts p ON p.set_id = mp.set_id
                AND p.part_num = mp.fig_num AND p.item_type = 'minifig'
            WHERE mp.set_id = ?
            """,
            (new_set_id, set_id),
        )

    flash(
        f"Nouvel exemplaire de {source['title']} ajouté ; ses pièces sont à vérifier.",
        "success",
    )
    return redirect(url_for("pieces_page" if destination == "pieces" else "sets_page"))


@app.post("/sets/<int:set_id>/complete-parts")
def complete_set_parts(set_id):
    with database() as connection:
        set_row = connection.execute(
            """
            SELECT s.title, COALESCE(SUM(p.missing_quantity), 0) AS missing
            FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
            WHERE s.id = ?
            GROUP BY s.id
            """,
            (set_id,),
        ).fetchone()
        if set_row is None:
            flash("Ce set n'existe plus.", "error")
            return redirect(url_for("pieces_page"))
        part_count = connection.execute(
            "SELECT COUNT(*) FROM set_parts WHERE set_id = ?", (set_id,)
        ).fetchone()[0]
        if not part_count:
            flash("Ajoutez d'abord les pièces du set avant de le compléter.", "error")
            return redirect(url_for("pieces_page"))
        if set_row["missing"]:
            connection.execute(
                "UPDATE set_parts SET missing_quantity = 0 WHERE set_id = ?",
                (set_id,),
            )
            connection.execute(
                "UPDATE minifig_parts SET missing_quantity = 0 WHERE set_id = ?",
                (set_id,),
            )
            connection.execute(
                "UPDATE sets SET in_gathering = 0 WHERE id = ? AND in_collection = 1",
                (set_id,),
            )
            message = f"Toutes les pièces de {set_row['title']} sont marquées comme trouvées."
        else:
            connection.execute(
                "UPDATE set_parts SET missing_quantity = quantity WHERE set_id = ?",
                (set_id,),
            )
            connection.execute(
                """
                UPDATE minifig_parts
                SET missing_quantity = quantity * COALESCE(
                    (SELECT p.quantity FROM set_parts p
                     WHERE p.set_id = minifig_parts.set_id
                       AND p.part_num = minifig_parts.fig_num
                       AND p.item_type = 'minifig'), 1)
                WHERE set_id = ?
                """,
                (set_id,),
            )
            connection.execute(
                "UPDATE sets SET in_gathering = 1, all_parts_found = 0 WHERE id = ?",
                (set_id,),
            )
            message = f"Toutes les pièces de {set_row['title']} sont à nouveau à chercher."
    flash(message, "success")
    destination = "sets_page" if request.form.get("return_to") == "sets" else "pieces_page"
    return redirect(url_for(destination))


@app.post("/sets/<int:set_id>/uncollect")
def uncollect_set(set_id):
    with database() as connection:
        cursor = connection.execute(
            "UPDATE sets SET in_collection = 0 WHERE id = ? AND in_collection = 1",
            (set_id,),
        )
    if cursor.rowcount:
        flash("Set retiré de Mes sets. Le suivi de ses pièces reste inchangé.", "success")
    else:
        flash("Ce set n'existe plus ou n'est pas dans Mes sets.", "error")
    return redirect(url_for("sets_page"))


@app.post("/sets/<int:set_id>/sold")
def sell_set(set_id):
    with database() as connection:
        cursor = connection.execute(
            """
            UPDATE sets
            SET in_collection = 0, in_gathering = 0
            WHERE id = ? AND in_collection = 1
            """,
            (set_id,),
        )
    if cursor.rowcount:
        flash("Set retiré de ta collection et de son suivi de pièces.", "success")
    else:
        flash("Ce set n'existe plus dans Mes sets.", "error")
    return redirect(url_for("sets_page"))


@app.post("/sets/<int:set_id>/parts")
def add_part(set_id):
    part_num = request.form.get("part_num", "").strip()
    part_name = request.form.get("part_name", "").strip() or part_num
    color_name = request.form.get("color_name", "").strip() or "Unknown"
    try:
        quantity = int(request.form.get("quantity", "1"))
        color_id = int(request.form.get("color_id", "0") or 0)
        if not part_num or quantity < 1 or color_id < 0:
            raise ValueError
    except ValueError:
        flash("Vérifiez la référence, la couleur et la quantité de la pièce.", "error")
        return redirect(url_for(_set_return_endpoint()))

    with database() as connection:
        set_row = connection.execute(
            "SELECT id, all_parts_found FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
        if not set_row:
            flash("Ce set n'existe plus.", "error")
            return redirect(url_for(_set_return_endpoint()))
        missing_quantity = 0 if set_row["all_parts_found"] else quantity
        connection.execute(
            """
            INSERT INTO set_parts
                (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(set_id, part_num, color_id) DO UPDATE SET
                quantity = quantity + excluded.quantity,
                missing_quantity = missing_quantity + excluded.missing_quantity,
                part_name = excluded.part_name,
                color_name = excluded.color_name
            """,
            (
                set_id,
                part_num,
                part_name,
                color_id,
                color_name,
                quantity,
                missing_quantity,
            ),
        )
    flash(f"Pièce {part_num} ajoutée.", "success")
    return redirect(url_for(_set_return_endpoint()))


def _set_return_endpoint():
    return {
        "pieces": "pieces_page",
        "sets": "sets_page",
    }.get(request.form.get("return_to"), "pieces_page")


@app.post("/parts/<int:part_id>/missing")
def update_missing(part_id):
    change = request.form.get("change")
    mark_complete = request.form.get("mark_complete") == "1"
    if change is not None and change not in {"-1", "1"}:
        flash("Le changement doit être une seule pièce en plus ou en moins.", "error")
        return redirect(url_for("pieces_page"))
    if change is None:
        if mark_complete:
            missing = 0
        else:
            try:
                missing = int(request.form.get("missing_quantity", ""))
                if missing < 0:
                    raise ValueError
            except ValueError:
                flash("La quantité manquante doit être un nombre positif ou zéro.", "error")
                destination = {
                    "missing": "missing_page",
                    "sets": "sets_page",
                    "pieces": "pieces_page",
                }.get(request.form.get("return_to"), "pieces_page")
                return redirect(url_for(destination))

    response_data = None
    with database() as connection:
        previous = connection.execute(
            "SELECT missing_quantity FROM set_parts WHERE id = ?", (part_id,)
        ).fetchone()
        if change is not None:
            cursor = connection.execute(
                """
                UPDATE set_parts
                SET missing_quantity = MIN(quantity, MAX(0, missing_quantity + ?))
                WHERE id = ?
                """,
                (int(change), part_id),
            )
        else:
            cursor = connection.execute(
                "UPDATE set_parts SET missing_quantity = MIN(?, quantity) WHERE id = ?",
                (missing, part_id),
            )
        if cursor.rowcount and previous:
            sync_minifig_components_from_parent(
                connection, part_id, previous["missing_quantity"]
            )
        if cursor.rowcount == 0:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Cette pièce n'existe plus."}), 404
            flash("Cette pièce n'existe plus.", "error")
        elif request.headers.get("X-Requested-With") == "XMLHttpRequest":
            part = connection.execute(
                """
                SELECT p.missing_quantity, p.quantity, p.part_num, p.color_id, p.set_id
                FROM set_parts p WHERE p.id = ?
                """,
                (part_id,),
            ).fetchone()
            gathering_cursor = connection.execute(
                """
                UPDATE sets
                SET in_gathering = 0
                WHERE id = ? AND in_collection = 1 AND in_gathering = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM set_parts
                      WHERE set_id = sets.id AND missing_quantity > 0
                  )
                """,
                (part["set_id"],),
            )
            gathering_complete = gathering_cursor.rowcount > 0
            part_missing = connection.execute(
                f"""
                SELECT COALESCE(SUM(p.missing_quantity), 0)
                FROM sets s JOIN set_parts p ON p.set_id = s.id
                WHERE s.{"in_collection" if request.form.get("return_to") == "missing" else "in_gathering"} = 1
                  AND p.part_num = ? AND p.color_id = ?
                """,
                (part["part_num"], part["color_id"]),
            ).fetchone()[0]
            total_missing = connection.execute(
                f"""
                SELECT COALESCE(SUM(p.missing_quantity), 0)
                FROM sets s JOIN set_parts p ON p.set_id = s.id
                WHERE s.{"in_collection" if request.form.get("return_to") == "missing" else "in_gathering"} = 1
                """
            ).fetchone()[0]
            set_missing = connection.execute(
                "SELECT COALESCE(SUM(missing_quantity), 0) FROM set_parts WHERE set_id = ?",
                (part["set_id"],),
            ).fetchone()[0]
            response_data = {
                "missing": part["missing_quantity"],
                "quantity": part["quantity"],
                "part_missing": part_missing,
                "total_missing": total_missing,
                "set_id": part["set_id"],
                "set_missing": set_missing,
                "gathering_complete": bool(gathering_complete),
            }
        elif cursor.rowcount:
            part = connection.execute(
                "SELECT set_id FROM set_parts WHERE id = ?", (part_id,)
            ).fetchone()
            connection.execute(
                """
                UPDATE sets
                SET in_gathering = 0
                WHERE id = ? AND in_collection = 1 AND in_gathering = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM set_parts
                      WHERE set_id = sets.id AND missing_quantity > 0
                  )
                """,
                (part["set_id"],),
            )
    if response_data is not None:
        return jsonify(response_data)
    destination = {
        "missing": "missing_page",
        "sets": "sets_page",
        "pieces": "pieces_page",
    }.get(request.form.get("return_to"), "pieces_page")
    return redirect(url_for(destination))


@app.post("/minifig-parts/<int:part_id>/status")
def update_minifig_part_status(part_id):
    status = request.form.get("status")
    change = request.form.get("change")
    mark_complete = request.form.get("mark_complete") == "1"
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not (
        (status in {"found", "missing"} and change is None and not mark_complete)
        or (change in {"-1", "1"} and status is None and not mark_complete)
        or (mark_complete and status is None and change is None)
    ):
        message = "La modification de la pièce est invalide."
        if is_ajax:
            return jsonify({"error": message}), 400
        flash(message, "error")
        return redirect(url_for("pieces_page"))

    with database() as connection:
        part = connection.execute(
            """
            SELECT mp.id, mp.set_id, mp.fig_num, mp.part_name, mp.missing_quantity,
                   mp.quantity * p.quantity AS quantity
            FROM minifig_parts mp
            JOIN set_parts p ON p.set_id = mp.set_id AND p.part_num = mp.fig_num
                AND p.item_type = 'minifig'
            WHERE mp.id = ?
            """,
            (part_id,),
        ).fetchone()
        if part is not None:
            if change is not None:
                missing = min(part["quantity"], max(0, part["missing_quantity"] + int(change)))
            elif status == "missing":
                missing = part["quantity"]
            else:
                missing = 0
            connection.execute(
                "UPDATE minifig_parts SET missing_quantity = ? WHERE id = ?",
                (missing, part_id),
            )
            sync_minifig_parent_from_components(connection, part["set_id"], part["fig_num"])
            connection.execute(
                """
                UPDATE sets SET in_gathering = 0
                WHERE id = ? AND in_collection = 1 AND in_gathering = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM set_parts
                      WHERE set_id = sets.id AND missing_quantity > 0
                  )
                """,
                (part["set_id"],),
            )

    if part is None:
        message = "Cette pièce de figurine n'existe plus."
        if is_ajax:
            return jsonify({"error": message}), 404
        flash(message, "error")
        return redirect(url_for("pieces_page"))
    if is_ajax:
        return jsonify(
            {
                "part_name": part["part_name"],
                "quantity": part["quantity"],
                "missing_quantity": missing,
            }
        )
    flash("Statut de la pièce de figurine mis à jour.", "success")
    return redirect(url_for("pieces_page"))


@app.post("/sets/<int:set_id>/delete")
def delete_set(set_id):
    with database() as connection:
        connection.execute("DELETE FROM minifig_parts WHERE set_id = ?", (set_id,))
        connection.execute("DELETE FROM sets WHERE id = ?", (set_id,))
    flash("Set supprimé de la liste à réunir ou de Mes sets.", "success")
    destination = {
        "pieces": "pieces_page",
        "sets": "sets_page",
    }.get(request.form.get("return_to"), "sets_page")
    return redirect(url_for(destination))


def get_export_quantities(owned):
    status_column = "in_collection" if owned else "in_gathering"
    with database() as connection:
        parts = connection.execute(
            f"""
            SELECT p.part_num, p.color_id, p.missing_quantity
            FROM sets s JOIN set_parts p ON p.set_id = s.id
            WHERE p.missing_quantity > 0 AND s.{status_column} = 1
                  AND p.item_type = 'part'
            ORDER BY p.part_num, p.color_id
            """
        ).fetchall()
    quantities = {}
    for part in parts:
        key = (part["part_num"], part["color_id"])
        quantities[key] = quantities.get(key, 0) + part["missing_quantity"]
    return quantities


def export_scope():
    scope = request.args.get("scope", "gather")
    if scope not in {"gather", "owned"}:
        abort(400)
    return scope == "owned"


@app.get("/export/bricklink.xml")
def export_bricklink():
    quantities = get_export_quantities(export_scope())
    root = ET.Element("INVENTORY")
    for (part_num, color_id), quantity in quantities.items():
        item = ET.SubElement(root, "ITEM")
        for tag, value in (
            ("ITEMTYPE", "P"),
            ("ITEMID", part_num),
            ("COLOR", color_id),
            ("MINQTY", quantity),
        ):
            ET.SubElement(item, tag).text = str(value)
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(payload, mimetype="application/xml", headers={"Content-Disposition": "attachment; filename=legolist-bricklink.xml"})


@app.get("/export/brickowl.csv")
def export_brickowl():
    quantities = get_export_quantities(export_scope())
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["ItemNo", "Color", "Qty"])
    for (part_num, color_id), quantity in quantities.items():
        writer.writerow([part_num, color_id, quantity])
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=legolist-brickowl.csv"},
    )


initialize_database()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
