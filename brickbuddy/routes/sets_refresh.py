"""Rafraîchissements d'un set depuis Rebrickable."""
from .. import db
from .. import inventory
from .. import prices
from .. import rebrickable
from .. import settings
from ..flask_app import app
from flask import flash, redirect, request, url_for

@app.post("/sets/<int:set_id>/refresh-image")
def refresh_set_image(set_id):
    with db.database() as connection:
        set_row = connection.execute(
            "SELECT set_num FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    if set_row is None:
        flash("Ce set n'existe plus.", "error")
        return redirect(url_for("sets_page"))
    try:
        set_info = rebrickable.fetch_set_info(set_row["set_num"])
    except (RuntimeError, ValueError) as error:
        flash(str(error), "error")
        return redirect(url_for("sets_page"))
    image_url = set_info.get("set_img_url") or ""
    if not image_url:
        flash(f"Rebrickable ne fournit pas d'image pour le set {set_row['set_num']}.", "error")
        return redirect(url_for("sets_page"))
    with db.database() as connection:
        connection.execute(
            "UPDATE sets SET set_image_url = ? WHERE id = ?",
            (image_url, set_id),
        )
    flash("Image du set récupérée depuis Rebrickable.", "success")
    return redirect(url_for("sets_page"))



@app.post("/sets/<int:set_id>/refresh-info")
def refresh_set_info(set_id):
    with db.database() as connection:
        set_row = connection.execute(
            "SELECT set_num FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    if set_row is None:
        flash("Ce set n'existe plus.", "error")
        return redirect(url_for("sets_page"))
    try:
        set_info = rebrickable.fetch_set_info(set_row["set_num"])
    except (RuntimeError, ValueError) as error:
        flash(str(error), "error")
        return redirect(url_for("sets_page"))
    year = set_info.get("year")
    if not isinstance(year, int):
        flash(f"Rebrickable ne fournit pas d'année pour le set {set_row['set_num']}.", "error")
        return redirect(url_for("sets_page"))
    with db.database() as connection:
        connection.execute("UPDATE sets SET year = ? WHERE id = ?", (year, set_id))
    flash(f"Année de sortie ({year}) récupérée depuis Rebrickable.", "success")
    return redirect(url_for("sets_page"))



@app.post("/sets/<int:set_id>/refresh-theme")
def refresh_set_theme(set_id):
    with db.database() as connection:
        set_row = connection.execute(
            "SELECT set_num FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    if set_row is None:
        flash("Ce set n'existe plus.", "error")
        return redirect(url_for("sets_page"))
    try:
        set_info = rebrickable.fetch_set_info(set_row["set_num"])
        theme_id = set_info.get("theme_id")
        if not theme_id:
            flash("Rebrickable ne fournit pas de thème pour ce set.", "error")
            return redirect(url_for("sets_page"))
        theme_name = rebrickable.fetch_theme_name(theme_id)
    except (RuntimeError, ValueError) as error:
        flash(str(error), "error")
        return redirect(url_for("sets_page"))
    with db.database() as connection:
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
    if not settings.setting_value("REBRICKABLE_API_KEY"):
        flash("Ajoute une clé API Rebrickable pour actualiser l'inventaire.", "error")
        return redirect(url_for(destination))
    with db.database() as connection:
        set_row = connection.execute(
            "SELECT set_num, all_parts_found FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    if set_row is None:
        flash("Ce set n'existe plus.", "error")
        return redirect(url_for(destination))
    try:
        _, parts = rebrickable.fetch_set_inventory(set_row["set_num"])
    except (RuntimeError, ValueError) as error:
        flash(str(error), "error")
        return redirect(url_for(destination))

    try:
        minifig_rows = rebrickable.fetch_minifig_parts_for_set(set_row["set_num"])
    except (RuntimeError, ValueError):
        minifig_rows = None

    with db.database() as connection:
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
                "brickowl_boid": part.get("brickowl_boid") or "",
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
        prices.remember_brickowl_boids(connection, list(merged.values()))
        if minifig_rows is not None:
            inventory.replace_set_minifig_parts(
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
