"""Images Rebrickable mises en cache local, couvertures des notices."""
from . import db
from . import instructions
from .flask_app import app
from flask import g, url_for
from pathlib import Path
import hashlib
import os
import urllib.parse

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
        str(db.DATABASE_PATH.parent / "rebrickable-images"),
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



def instruction_cover_url(source_url):
    """Couverture LEGO correspondant au PDF officiel d'une notice enregistrée."""
    if not source_url or not instructions.lego_instruction_url(source_url):
        return ""
    cover = source_url.replace("/product.bi.core.pdf/", "/product.bi.core.img/")
    cover = cover[: -len(".pdf")] + ".png"
    return cover if instructions.lego_instruction_image_url(cover) else ""

# Les gabarits utilisent ces deux noms comme filtres Jinja.
app.jinja_env.filters["local_image_url"] = local_image_url
app.jinja_env.filters["instruction_cover"] = instruction_cover_url
