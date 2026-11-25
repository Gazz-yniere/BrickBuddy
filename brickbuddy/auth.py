"""Mot de passe partagé, jeton CSRF, cible de redirection sûre."""
from .flask_app import app
from flask import request, session, url_for
import hashlib
import hmac
import os
import urllib.parse


def form_csrf_ok():
    """Le jeton de la session correspond-il à celui du formulaire envoyé ?"""
    token = session.get("csrf_token", "")
    return bool(token) and hmac.compare_digest(token, request.form.get("csrf_token", ""))

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
