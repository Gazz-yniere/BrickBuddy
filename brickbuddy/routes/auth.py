"""Connexion, déconnexion, garde d'accès."""
from .. import auth
from ..flask_app import app
from flask import abort, redirect, render_template, request, session, url_for
import hmac
import os
import secrets
import urllib.parse

@app.before_request
def require_login():
    if request.endpoint in {"login", "login_submit", "health", "static"}:
        return None
    config_error = auth.authentication_config_error()
    if config_error:
        return redirect(url_for("login", next=request.path))
    if (
        not session.get("authenticated")
        or not hmac.compare_digest(
            session.get("auth_version", ""), auth.authentication_version()
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
    config_error = auth.authentication_config_error()
    if config_error:
        app.logger.error("Authentication is unavailable: %s", config_error)
        return render_template(
            "login.html",
            config_error="La connexion n'est pas encore configurée. Consultez le README pour configurer l'accès.",
        ), 503

    next_target = auth.safe_redirect_target(request.args.get("next", ""))
    if session.get("authenticated"):
        if hmac.compare_digest(
            session.get("auth_version", ""), auth.authentication_version()
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
    config_error = auth.authentication_config_error()
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
            next_target=auth.safe_redirect_target(request.form.get("next", "")),
            csrf_token=csrf_token,
            error="Mot de passe incorrect.",
            config_error=None,
        ), 401

    session.clear()
    session.permanent = True
    session["authenticated"] = True
    session["auth_version"] = auth.authentication_version()
    session["csrf_token"] = secrets.token_urlsafe(32)
    return redirect(auth.safe_redirect_target(request.form.get("next", "")))



@app.post("/logout")
def logout():
    csrf_token = session.get("csrf_token", "")
    submitted_csrf = request.form.get("csrf_token", "")
    if not csrf_token or not hmac.compare_digest(csrf_token, submitted_csrf):
        abort(400, description="Formulaire de déconnexion expiré. Rechargez la page.")
    session.clear()
    return redirect(url_for("login"))
