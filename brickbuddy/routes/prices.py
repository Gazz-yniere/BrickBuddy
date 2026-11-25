"""Bouton de relève forcée des prix, sur la page Paramètres."""
from .. import instructions
from .. import prices
from ..flask_app import app
from flask import flash, redirect, url_for

@app.post("/parametres/prix/rafraichir")
def refresh_prices():
    """Relance la relève de toutes les pièces possédées, sans attendre le relevé du jour."""
    instructions.check_instruction_csrf()
    if not prices.prices_enabled():
        flash("L'affichage des prix est désactivé : activez « Afficher les prix », avec une clé BrickOwl.", "error")
        return redirect(url_for("settings_page"))
    if prices.price_refresh_running():
        flash("Une relève des prix est déjà en cours, elle se termine en arrière-plan.", "success")
        return redirect(url_for("settings_page"))
    if prices.claim_price_refresh(force=True):
        flash("Relève des prix lancée : toutes tes pièces sont relevées une à une, en arrière-plan.", "success")
    else:
        flash("La relève des prix n'a pas pu démarrer, réessayez dans quelques minutes.", "error")
    return redirect(url_for("settings_page"))
