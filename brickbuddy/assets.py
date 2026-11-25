"""Version des fichiers statiques et en-têtes de cache."""
from . import db
from .flask_app import app
from flask import g, request
from pathlib import Path
import hashlib
import threading

_asset_versions = {}



_asset_versions_lock = threading.Lock()



def asset_version(filename):
    """Signature courte du fichier statique, utilisée comme ?v= dans les pages.

    Le numéro change tout seul quand le fichier change : on ne peut plus oublier
    de le augmenter, une page ne pointe jamais sur une adresse périmée et un
    fichier absent n'est jamais réclamé deux fois sous la même adresse.
    """
    path = Path(app.static_folder) / filename
    try:
        stat = path.stat()
    except OSError:
        return "0"
    signature = (str(path), stat.st_mtime_ns, stat.st_size)
    with _asset_versions_lock:
        cached = _asset_versions.get(filename)
        if cached is not None and cached[0] == signature:
            return cached[1]
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        except OSError:
            digest = "0"
        _asset_versions[filename] = (signature, digest)
        return digest



@app.context_processor
def template_assets():
    return {"asset_version": asset_version}



@app.after_request
def cache_policy_headers(response):
    """Pages jamais mises en cache, fichiers versionnés très longtemps.

    Sans cela le navigateur garde une vieille page qui réclame un CSS devenu
    étranger : la page s'affiche alors en texte brut, sans structure.
    Seules les réponses réussies sont gardées un an : une adresse de CSS
    introuvable est servie sans cache, sinon le navigateur la répète pendant
    des mois et la page reste sans feuille de style.
    """
    if request.path.startswith("/static/"):
        if response.status_code in {200, 204, 304}:
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        elif response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
    elif "text/html" in response.content_type:
        response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
    return response



@app.after_request
def cache_rebrickable_image_urls(response):
    pending_images = getattr(g, "pending_rebrickable_images", None)
    if pending_images:
        with db.database() as connection:
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
