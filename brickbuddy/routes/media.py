"""Images Rebrickable servies depuis le cache local."""
from .. import db
from .. import images
from ..flask_app import app
from flask import Response, abort, send_file
from pathlib import Path
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

@app.get("/media/rebrickable/<image_key>")
def cached_rebrickable_image(image_key):
    if not re.fullmatch(r"[a-f0-9]{64}", image_key):
        abort(404)
    with db.database() as connection:
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
    extension = images.IMAGE_TYPES.get(content_type)
    image_path = images.IMAGE_CACHE_PATH / f"{image_key}{extension}" if extension else None
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
        or parsed.hostname not in images.ALLOWED_IMAGE_HOSTS
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
                or final_url.hostname not in images.ALLOWED_IMAGE_HOSTS
                or final_url.port not in (None, 443)
                or final_url.username
                or final_url.password
            ):
                raise ValueError("Le serveur d'image a redirigé vers un domaine non autorisé.")
            declared_content_type = response.headers.get_content_type()
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > images.MAX_CACHED_IMAGE_BYTES:
                raise ValueError("L'image Rebrickable dépasse la taille maximale autorisée.")
            image_bytes = response.read(images.MAX_CACHED_IMAGE_BYTES + 1)
            if len(image_bytes) > images.MAX_CACHED_IMAGE_BYTES:
                raise ValueError("L'image Rebrickable dépasse la taille maximale autorisée.")
            content_type = next(
                (
                    image_type
                    for image_type, signature_check in images.IMAGE_SIGNATURES.items()
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
            extension = images.IMAGE_TYPES[content_type]
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
        app.logger.warning("Impossible de mettre en cache une image Rebrickable: %s", error)
        return Response("Image Rebrickable indisponible.", status=502, mimetype="text/plain")

    images.IMAGE_CACHE_PATH.mkdir(parents=True, exist_ok=True)
    image_path = images.IMAGE_CACHE_PATH / f"{image_key}{extension}"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=images.IMAGE_CACHE_PATH, prefix=f"{image_key}.", suffix=".tmp", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(image_bytes)
        os.replace(temporary_path, image_path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
    with db.database() as connection:
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
