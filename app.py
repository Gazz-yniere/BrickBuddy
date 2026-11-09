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

LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5


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


def login_attempt_key():
    secret_key = app.secret_key.encode("utf-8")
    address = request.remote_addr or "unknown"
    return hmac.new(secret_key, address.encode("utf-8"), hashlib.sha256).hexdigest()


def authentication_version():
    password = os.environ["APP_PASSWORD"]
    return hmac.new(
        app.secret_key.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get_login_lockout(attempt_key, now):
    with database() as connection:
        row = connection.execute(
            "SELECT locked_until FROM login_attempts WHERE address_hash = ?",
            (attempt_key,),
        ).fetchone()
    return max(0, row["locked_until"] - now) if row else 0


def record_failed_login(attempt_key, now):
    with database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT attempts, window_started_at, locked_until
            FROM login_attempts WHERE address_hash = ?
            """,
            (attempt_key,),
        ).fetchone()
        if row and row["locked_until"] > now:
            return row["locked_until"] - now

        if row and now - row["window_started_at"] < LOGIN_ATTEMPT_WINDOW_SECONDS:
            attempts = row["attempts"] + 1
            window_started_at = row["window_started_at"]
        else:
            attempts = 1
            window_started_at = now
        locked_until = (
            now + LOGIN_ATTEMPT_WINDOW_SECONDS
            if attempts >= LOGIN_MAX_ATTEMPTS
            else 0
        )
        connection.execute(
            """
            INSERT INTO login_attempts
                (address_hash, attempts, window_started_at, locked_until)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(address_hash) DO UPDATE SET
                attempts = excluded.attempts,
                window_started_at = excluded.window_started_at,
                locked_until = excluded.locked_until
            """,
            (attempt_key, attempts, window_started_at, locked_until),
        )
        connection.execute(
            """
            DELETE FROM login_attempts
            WHERE address_hash != ?
              AND locked_until <= ?
              AND window_started_at < ?
            """,
            (
                attempt_key,
                now,
                now - LOGIN_ATTEMPT_WINDOW_SECONDS,
            ),
        )
    return max(0, locked_until - now)


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

    attempt_key = login_attempt_key()
    now = time.time()
    retry_after = get_login_lockout(attempt_key, now)
    if retry_after:
        response = make_response(
            render_template(
                "login.html",
                next_target=safe_redirect_target(request.form.get("next", "")),
                csrf_token=csrf_token,
                error="Trop de tentatives. Réessayez dans 15 minutes.",
                config_error=None,
            ),
            429,
        )
        response.headers["Retry-After"] = str(int(retry_after))
        return response

    password_matches = hmac.compare_digest(
        os.environ["APP_PASSWORD"].encode("utf-8"),
        request.form.get("password", "").encode("utf-8"),
    )

    if not password_matches:
        retry_after = record_failed_login(attempt_key, now)
        app.logger.warning("Rejected login attempt")
        message = (
            "Trop de tentatives. Réessayez dans 15 minutes."
            if retry_after
            else "Mot de passe incorrect."
        )
        response = make_response(
            render_template(
                "login.html",
                next_target=safe_redirect_target(request.form.get("next", "")),
                csrf_token=csrf_token,
                error=message,
                config_error=None,
            ),
            429 if retry_after else 401,
        )
        if retry_after:
            response.headers["Retry-After"] = str(int(retry_after))
        return response

    with database() as connection:
        connection.execute(
            "DELETE FROM login_attempts WHERE address_hash = ?", (attempt_key,)
        )
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
                UNIQUE(set_id, part_num, color_id)
            );
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
            CREATE TABLE IF NOT EXISTS login_attempts (
                address_hash TEXT PRIMARY KEY,
                attempts INTEGER NOT NULL,
                window_started_at REAL NOT NULL,
                locked_until REAL NOT NULL DEFAULT 0
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
                },
            )
            entry["quantity"] += int(item.get("quantity") or 0)
        next_page = page.get("next")
        if next_page:
            parsed = urllib.parse.urlparse(next_page)
            next_page = parsed.path.removeprefix("/api/v3/lego/")
            if parsed.query:
                next_page += f"?{parsed.query}"
    return set_info, list(parts.values())


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
               s.theme_name, s.in_gathering,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num AND other.id <= s.id
                  AND other.{copy_state} = 1) AS copy_number,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num
                  AND other.{copy_state} = 1) AS copy_count,
               p.id AS part_id, p.part_num, p.part_name, p.color_id,
               p.color_name, p.quantity, p.missing_quantity, p.image_url
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
                "copy_number": row["copy_number"],
                "copy_count": row["copy_count"],
                "quantity": row["quantity"],
                "missing": row["missing_quantity"],
                "part_id": row["part_id"],
            }
        )

    sort_keys = {
        "color": lambda item: (item["color_name"].casefold(), item["part_name"].casefold()),
        "name": lambda item: (item["part_name"].casefold(), item["color_name"].casefold()),
        "missing": lambda item: (-item["missing"], item["color_name"].casefold(), item["part_name"].casefold()),
        "quantity": lambda item: (-item["quantity"], item["color_name"].casefold(), item["part_name"].casefold()),
    }
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
                SELECT s.id, s.set_num, s.title, s.set_image_url, s.in_collection,
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
    )


@app.get("/inventaire")
def inventory_page():
    search = request.args.get("q", "").strip()
    color_filter = request.args.get("color", "").strip()
    where = ["s.in_collection = 1", "p.quantity > p.missing_quantity"]
    params = []
    if search:
        where.append(
            "(s.set_num LIKE ? OR s.title LIKE ? OR p.part_num LIKE ? "
            "OR p.part_name LIKE ? OR p.color_name LIKE ?)"
        )
        params.extend([f"%{search}%"] * 5)
    if color_filter:
        where.append("p.color_name = ?")
        params.append(color_filter)
    sql = f"""
        SELECT p.part_num, p.part_name, p.color_id, p.color_name,
               SUM(p.quantity - p.missing_quantity) AS quantity,
               MAX(p.image_url) AS image_url
        FROM sets s JOIN set_parts p ON p.set_id = s.id
        WHERE {" AND ".join(where)}
        GROUP BY p.part_num, p.color_id, p.part_name, p.color_name
        ORDER BY p.color_name COLLATE NOCASE, p.part_name COLLATE NOCASE,
                 p.part_num
    """
    with database() as connection:
        rows = connection.execute(sql, params).fetchall()
        colors = [
            row["color_name"]
            for row in connection.execute(
                """
                SELECT DISTINCT p.color_name
                FROM sets s JOIN set_parts p ON p.set_id = s.id
                WHERE s.in_collection = 1 AND p.quantity > p.missing_quantity
                ORDER BY p.color_name COLLATE NOCASE
                """
            ).fetchall()
        ]

    color_groups = {}
    total_quantity = 0
    for row in rows:
        group = color_groups.setdefault(
            row["color_name"], {"name": row["color_name"], "parts": [], "quantity": 0}
        )
        group["parts"].append(dict(row))
        group["quantity"] += row["quantity"]
        total_quantity += row["quantity"]

    return render_template(
        "inventory.html",
        groups=list(color_groups.values()),
        colors=colors,
        color_filter=color_filter,
        search=search,
        total_quantity=total_quantity,
        part_count=sum(len(group["parts"]) for group in color_groups.values()),
    )


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
            )
            for part in parts
        ]
        connection.executemany(
            """
            INSERT INTO set_parts
                (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity, image_url)
            VALUES
                (:set_id, :part_num, :part_name, :color_id, :color_name, :quantity, :missing_quantity, :image_url)
            """,
            imported_parts,
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
                 quantity, missing_quantity, image_url)
            SELECT ?, part_num, part_name, color_id, color_name,
                   quantity, quantity, image_url
            FROM set_parts WHERE set_id = ?
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


@app.post("/sets/<int:set_id>/delete")
def delete_set(set_id):
    with database() as connection:
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
