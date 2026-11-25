"""Écran « Construire » : recherche, upload, lecture des notices."""
from .. import config
from .. import db
from .. import instructions
from ..flask_app import app
from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.exceptions import RequestEntityTooLarge
import http.client
import re
import urllib.error
import urllib.parse
import urllib.request

@app.get("/sets/<int:set_id>/notices")
def set_instructions(set_id):
    item = instructions.instruction_set(set_id)
    manuals = instructions.saved_instructions(item["set_num"])
    selected_id = request.args.get("notice", "")
    selected = next((manual for manual in manuals if manual["id"] == selected_id), None)
    if selected_id and selected is None:
        abort(404)
    if not selected_id and manuals:
        selected = manuals[0]
    # Flèches du carrousel : elles désignent la notice voisine, en faisant le
    # tour du carrousel (la gauche ramène au dernier livre, la droite au premier).
    selected_index = next(
        (index for index, manual in enumerate(manuals) if manual == selected), 0
    )
    previous_manual = manuals[selected_index - 1] if len(manuals) > 1 else None
    next_manual = manuals[(selected_index + 1) % len(manuals)] if len(manuals) > 1 else None
    official = None
    error = None
    search_requested = request.args.get("rechercher") == "1"
    # Le bouton « Construire » n'appelle jamais LEGO côté serveur : la page
    # s'affiche immédiatement puis la recherche est lancée par le navigateur,
    # y compris quand des notices sont déjà enregistrées (badges « Enregistrée »).
    auto_search = request.args.get("construire") == "1"
    if search_requested:
        try:
            official = instructions.find_lego_instructions(item["set_num"])
            saved_urls = {manual["source_url"] for manual in manuals if manual["source_url"]}
            for instruction in official:
                instruction["saved"] = instruction["url"] in saved_urls
        except (RuntimeError, ValueError) as exc:
            error = str(exc)
    return render_template(
        "instructions.html", set=item, manuals=manuals, selected=selected,
        previous_manual=previous_manual, next_manual=next_manual,
        official=official, search_error=error, auto_search=auto_search,
    )



@app.get("/sets/<int:set_id>/notices/rechercher")
def search_instructions(set_id):
    item = instructions.instruction_set(set_id)
    with db.database() as connection:
        saved_urls = {
            row["source_url"]
            for row in connection.execute(
                """SELECT source_url FROM set_instructions
                   WHERE set_num = ? AND source_url IS NOT NULL AND source_url != ''""",
                (item["set_num"],),
            )
        }
    official = None
    error = None
    try:
        official = instructions.find_lego_instructions(item["set_num"])
        for instruction in official:
            instruction["saved"] = instruction["url"] in saved_urls
    except (RuntimeError, ValueError) as exc:
        error = str(exc)
    return render_template(
        "_instruction_results.html", set=item, manuals=instructions.saved_instructions(item["set_num"]),
        official=official, search_error=error,
    )



@app.post("/sets/<int:set_id>/notices")
def upload_instruction(set_id):
    item = instructions.instruction_set(set_id)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    try:
        instructions.check_instruction_csrf()
        upload = request.files.get("notice")
    except RequestEntityTooLarge:
        message = "La notice dépasse la limite de 200 Mo."
        if is_ajax:
            return jsonify({"error": message}), 400
        flash(message, "error")
        return redirect(url_for("set_instructions", set_id=set_id))
    if not upload or not upload.filename:
        message = "Choisis un fichier PDF."
        if is_ajax:
            return jsonify({"error": message}), 400
        flash(message, "error")
        return redirect(url_for("set_instructions", set_id=set_id))
    filename = upload.filename.replace("\\", "/").rsplit("/", 1)[-1][:255]
    if not filename.lower().endswith(".pdf"):
        message = "La notice doit être un fichier PDF."
        if is_ajax:
            return jsonify({"error": message}), 400
        flash(message, "error")
        return redirect(url_for("set_instructions", set_id=set_id))
    try:
        notice_id = instructions.save_instruction(item["set_num"], filename, upload.stream)
    except ValueError as error:
        if is_ajax:
            return jsonify({"error": str(error)}), 400
        flash(str(error), "error")
        return redirect(url_for("set_instructions", set_id=set_id))
    if is_ajax:
        # La notice ajoutee rejoint le carrousel sans rechargement : la liste
        # des livres trouves chez LEGO reste affichee sous ses numeros.
        return jsonify(instructions.instruction_card_payload(
            item, instructions.saved_instructions(item["set_num"]), notice_id
        ))
    flash("Notice ajoutée.", "success")
    return redirect(url_for("set_instructions", set_id=set_id, notice=notice_id))



@app.post("/sets/<int:set_id>/notices/telecharger")
def download_instruction(set_id):
    item = instructions.instruction_set(set_id)
    instructions.check_instruction_csrf()
    url = request.form.get("url", "")
    if not instructions.lego_instruction_url(url):
        abort(400, description="Adresse de notice LEGO invalide.")
    title = request.form.get("title", "").strip()[:255]
    position_raw = request.form.get("position", "")
    if position_raw and (not position_raw.isascii() or not position_raw.isdecimal() or len(position_raw) > 5):
        abort(400, description="Position de notice invalide.")
    position = int(position_raw) if position_raw else None
    search_return = request.form.get("search_return") == "1"
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    def destination(notice_id=None):
        return url_for("set_instructions", set_id=set_id, notice=notice_id,
                       rechercher="1" if search_return else None)
    with db.database() as connection:
        existing = connection.execute(
            "SELECT id FROM set_instructions WHERE set_num = ? AND source_url = ?",
            (item["set_num"], url),
        ).fetchone()
    if existing:
        if not (instructions.instruction_directory() / f"{existing['id']}.pdf").is_file():
            message = "Le fichier enregistré est introuvable. Supprime la notice avant de la télécharger à nouveau."
            if is_ajax:
                return jsonify({"error": message}), 409
            flash(message, "error")
            return redirect(destination())
        if position is not None:
            with db.database() as connection:
                connection.execute(
                    "UPDATE set_instructions SET display_title = ?, source_position = ? WHERE id = ?",
                    (title, position, existing["id"]),
                )
        if is_ajax:
            return jsonify(instructions.instruction_card_payload(
                item, instructions.saved_instructions(item["set_num"]), existing["id"]
            ))
        flash("Cette notice est déjà enregistrée.", "success")
        return redirect(destination(existing["id"]))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.build_opener(instructions.LegoPdfRedirectHandler()).open(req, timeout=30) as response:
            length = response.headers.get("Content-Length")
            expected_length = int(length) if length else None
            if expected_length is not None and expected_length > config.MAX_INSTRUCTION_BYTES:
                raise ValueError("La notice dépasse la limite de 200 Mo.")
            filename = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])[:255]
            notice_id = instructions.save_instruction(
                item["set_num"], filename, response, url, expected_length, title, position
            )
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, http.client.HTTPException) as error:
        app.logger.warning("Téléchargement de la notice LEGO impossible : %s", error)
        message = f"Impossible d'enregistrer la notice : {error}"
        if is_ajax:
            return jsonify({"error": message}), 502
        flash(message, "error")
        return redirect(destination())
    if is_ajax:
        return jsonify(instructions.instruction_card_payload(
            item, instructions.saved_instructions(item["set_num"]), notice_id
        ))
    flash("Notice LEGO enregistrée localement.", "success")
    return redirect(destination(notice_id))



@app.get("/sets/<int:set_id>/notices/<notice_id>/pdf")
def instruction_pdf(set_id, notice_id):
    item = instructions.instruction_set(set_id)
    with db.database() as connection:
        manual = connection.execute(
            "SELECT filename FROM set_instructions WHERE id = ? AND set_num = ?",
            (notice_id, item["set_num"]),
        ).fetchone()
    if manual is None or not re.fullmatch(r"[a-f0-9]{32}", notice_id):
        abort(404)
    path = instructions.instruction_directory() / f"{notice_id}.pdf"
    if not path.is_file():
        app.logger.error("Fichier de notice manquant : %s", notice_id)
        abort(404, description="Le fichier de cette notice est introuvable.")
    response = send_file(
        path,
        mimetype="application/pdf",
        download_name=manual["filename"],
        conditional=True,
        max_age=31536000,
    )
    # L'identifiant de notice designe un fichier qui ne change jamais : la
    # reponse est immuable, le navigateur la relit sans revalidation et le
    # lecteur affiche la notice instantanement.
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response



@app.post("/sets/<int:set_id>/notices/<notice_id>/supprimer")
def delete_instruction(set_id, notice_id):
    item = instructions.instruction_set(set_id)
    instructions.check_instruction_csrf()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    with db.database() as connection:
        manual = connection.execute(
            """SELECT id, filename, display_title, source_url, source_position
               FROM set_instructions WHERE id = ? AND set_num = ?""",
            (notice_id, item["set_num"]),
        ).fetchone()
        if manual is None or not re.fullmatch(r"[a-f0-9]{32}", notice_id):
            abort(404)
        path = instructions.instruction_directory() / f"{notice_id}.pdf"
        if not path.is_file():
            app.logger.warning("Fichier de notice déjà absent : %s", notice_id)
        else:
            try:
                path.unlink()
            except OSError as error:
                app.logger.warning("Suppression de la notice impossible : %s", error)
                message = "Impossible de supprimer la notice. Ferme-la et réessaie."
                if is_ajax:
                    return jsonify({"error": message}), 409
                flash(message, "error")
                return redirect(url_for("set_instructions", set_id=set_id))
        connection.execute("DELETE FROM set_instructions WHERE id = ?", (notice_id,))
    if is_ajax:
        # Le livre retire redevient une proposition LEGO : le carrousel conserve
        # la liste complete des livres trouves, la page n'est pas rechargee.
        return jsonify({
            "deleted": True,
            "notice_id": notice_id,
            "tile_html": instructions.proposal_tile_html(item, manual),
        })
    flash("Notice supprimée pour tous les exemplaires de cette référence.", "success")
    return redirect(url_for("set_instructions", set_id=set_id))
