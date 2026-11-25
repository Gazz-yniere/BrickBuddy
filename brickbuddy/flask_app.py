"""L'application Flask : une seule instance partagée par tous les modules."""
import os
from datetime import timedelta

from flask import Flask
from flask_compress import Compress

from .config import BASE_DIR, MAX_INSTRUCTION_BYTES

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.secret_key = os.environ.get("SECRET_KEY")
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").casefold()
    in {"1", "true", "yes", "on"},
    MAX_CONTENT_LENGTH=MAX_INSTRUCTION_BYTES + 1024 * 1024,
    # Les fichiers statiques portent un ?v= calculé sur leur contenu : ils peuvent
    # être gardés un an en cache, une page ne demande jamais le CSS d'une version
    # dépassée et ne peut pas garder en mémoire une adresse devenue introuvable.
    SEND_FILE_MAX_AGE_DEFAULT=timedelta(days=365),
)
# HTML et CSS/JS comprimés : premier affichage nettement plus rapide.
Compress(app)
