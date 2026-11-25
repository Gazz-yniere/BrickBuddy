"""Écritures du vrac et des pièces manquantes."""
from .. import db
from .. import inventory
from ..flask_app import app
from flask import flash, jsonify, redirect, request, url_for

@app.post("/stock")
def add_stock_part():
    part_num = request.form.get("part_num", "").strip()
    part_name = request.form.get("part_name", "").strip() or part_num
    color_name = request.form.get("color_name", "").strip() or "Unknown"
    item_type = request.form.get("item_type", "").strip().lower() or "part"
    if item_type not in {"part", "minifig"}:
        item_type = "part"
    image_url = request.form.get("image_url", "").strip()
    raw_color_id = request.form.get("color_id", "").strip()
    try:
        color_id = int(raw_color_id) if raw_color_id else 0
    except (TypeError, ValueError):
        flash("Couleur invalide pour cette pièce du vrac.", "error")
        return redirect(url_for("inventory_page"))
    if color_id < 0:
        flash("Couleur invalide pour cette pièce du vrac.", "error")
        return redirect(url_for("inventory_page"))
    try:
        quantity = int(request.form.get("quantity", "0"))
    except (TypeError, ValueError):
        quantity = 0
    if not part_num or quantity <= 0:
        flash("Indiquez une référence et une quantité valide pour le vrac.", "error")
        return redirect(url_for("inventory_page"))
    with db.database() as connection:
        connection.execute(
            """
            INSERT INTO stock_parts
                (part_num, color_id, part_name, color_name, item_type, image_url, quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(part_num, color_id) DO UPDATE SET
                quantity = stock_parts.quantity + excluded.quantity,
                part_name = excluded.part_name,
                color_name = excluded.color_name,
                item_type = excluded.item_type,
                image_url = CASE WHEN excluded.image_url != ''
                                 THEN excluded.image_url
                                 ELSE stock_parts.image_url END
            """,
            (part_num, color_id, part_name, color_name, item_type, image_url, quantity),
        )
    flash(f"{quantity} × {part_name} ajouté(s) au vrac.", "success")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        # La réponse JSON ne porte pas le message : la page redemandée le affiche.
        with db.database() as connection:
            return inventory._stock_update_response(connection, part_num, color_id)
    return redirect(url_for("inventory_page"))



@app.post("/stock/<int:stock_id>/adjust")
def adjust_stock_part(stock_id):
    with db.database() as connection:
        row = connection.execute(
            """
            SELECT id, part_num, color_id, part_name, quantity
            FROM stock_parts WHERE id = ?
            """,
            (stock_id,),
        ).fetchone()
    if row is None:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Cette entrée du vrac n'existe plus."}), 404
        flash("Cette entrée du vrac n'existe plus.", "error")
        return redirect(url_for("inventory_page"))
    form_quantity = request.form.get("quantity")
    if form_quantity is not None and form_quantity.strip() != "":
        try:
            quantity = int(form_quantity)
            if quantity < 0:
                raise ValueError
        except (TypeError, ValueError):
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Quantité invalide."}), 400
            flash("Quantité invalide.", "error")
            return redirect(url_for("inventory_page"))
    else:
        try:
            change = int(request.form.get("change", "0"))
        except (TypeError, ValueError):
            change = 0
        quantity = row["quantity"] + change
    if quantity <= 0:
        with db.database() as connection:
            connection.execute("DELETE FROM stock_parts WHERE id = ?", (stock_id,))
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return inventory._stock_update_response(
                    connection, row["part_num"], row["color_id"]
                )
        flash(f"{row['part_name']} retiré du vrac.", "success")
        return redirect(url_for("inventory_page"))
    with db.database() as connection:
        connection.execute(
            "UPDATE stock_parts SET quantity = ? WHERE id = ?",
            (quantity, stock_id),
        )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        with db.database() as connection:
            return inventory._stock_update_response(
                connection, row["part_num"], row["color_id"]
            )
    flash(f"{row['part_name']} : {quantity} dans le vrac.", "success")
    return redirect(url_for("inventory_page"))



@app.post("/stock/<int:stock_id>/delete")
def delete_stock_part(stock_id):
    with db.database() as connection:
        row = connection.execute(
            "SELECT part_name, part_num, color_id FROM stock_parts WHERE id = ?",
            (stock_id,),
        ).fetchone()
        if row is None:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Cette entrée du vrac n'existe plus."}), 404
            flash("Cette entrée du vrac n'existe plus.", "error")
            return redirect(url_for("inventory_page"))
        connection.execute("DELETE FROM stock_parts WHERE id = ?", (stock_id,))
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return inventory._stock_update_response(connection, row["part_num"], row["color_id"])
    flash(f"{row['part_name']} retiré du vrac.", "success")
    return redirect(url_for("inventory_page"))



@app.post("/pieces/take-stock")
def take_stock_for_part():
    part_num = request.form.get("part_num", "")
    try:
        color_id = int(request.form.get("color_id", ""))
    except ValueError:
        flash("Pièce invalide.", "error")
        return redirect(url_for("pieces_page"))
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    updates = []
    taken = 0
    available = 0
    with db.database() as connection:
        stock = connection.execute(
            "SELECT id, quantity FROM stock_parts WHERE part_num = ? AND color_id = ?",
            (part_num, color_id),
        ).fetchone()
        if stock is not None and stock["quantity"] > 0:
            rows = connection.execute(
                """
                SELECT sp.id, sp.missing_quantity, sp.item_type
                FROM set_parts sp JOIN sets s ON s.id = sp.set_id
                WHERE sp.part_num = ? AND sp.color_id = ? AND s.in_gathering = 1
                  AND sp.missing_quantity > 0
                ORDER BY s.created_at, s.id
                """,
                (part_num, color_id),
            ).fetchall()
            available = stock["quantity"]
            for row in rows:
                take = min(row["missing_quantity"], available)
                if take <= 0:
                    break
                connection.execute(
                    "UPDATE set_parts SET missing_quantity = ? WHERE id = ?",
                    (row["missing_quantity"] - take, row["id"]),
                )
                inventory.sync_minifig_components_from_parent(
                    connection, row["id"], row["missing_quantity"]
                )
                updates.append(
                    {
                        "part_id": row["id"],
                        "missing": row["missing_quantity"] - take,
                        "item_type": row["item_type"],
                    }
                )
                available -= take
                taken += take
            if taken:
                if available <= 0:
                    connection.execute(
                        "DELETE FROM stock_parts WHERE id = ?", (stock["id"],)
                    )
                else:
                    connection.execute(
                        "UPDATE stock_parts SET quantity = ? WHERE id = ?",
                        (available, stock["id"]),
                    )
    if ajax:
        if not taken:
            return jsonify({"error": "Aucune pièce du vrac à utiliser pour cette référence."}), 400
        return jsonify({"taken": taken, "stock_qty": available, "updates": updates})
    if taken:
        flash(f"{taken} pièce{'s' if taken > 1 else ''} prise{'s' if taken > 1 else ''} dans le vrac.", "success")
    else:
        flash("Aucune pièce du vrac à utiliser pour cette référence.", "error")
    return redirect(url_for("pieces_page"))



@app.post("/sets/<int:set_id>/take-stock")
def take_stock_for_set(set_id):
    return_to = request.form.get("return_to", "")
    with db.database() as connection:
        rows = connection.execute(
            """
            SELECT sp.id AS sp_id, sp.missing_quantity,
                   st.id AS stock_id, st.quantity AS stock_quantity
            FROM set_parts sp
            JOIN sets s ON s.id = sp.set_id
            JOIN stock_parts st
              ON st.part_num = sp.part_num AND st.color_id = sp.color_id
            WHERE sp.set_id = ? AND s.in_gathering = 1
              AND sp.missing_quantity > 0 AND st.quantity > 0
            """,
            (set_id,),
        ).fetchall()
        taken = 0
        for row in rows:
            take = min(row["missing_quantity"], row["stock_quantity"])
            if take <= 0:
                continue
            taken += take
            connection.execute(
                "UPDATE set_parts SET missing_quantity = ? WHERE id = ?",
                (row["missing_quantity"] - take, row["sp_id"]),
            )
            inventory.sync_minifig_components_from_parent(
                connection, row["sp_id"], row["missing_quantity"]
            )
            remaining = row["stock_quantity"] - take
            if remaining <= 0:
                connection.execute(
                    "DELETE FROM stock_parts WHERE id = ?", (row["stock_id"],)
                )
            else:
                connection.execute(
                    "UPDATE stock_parts SET quantity = ? WHERE id = ?",
                    (remaining, row["stock_id"]),
                )
    if taken > 0:
        flash(
            f"{taken} pièce{'s' if taken > 1 else ''} "
            f"prise{'s' if taken > 1 else ''} "
            "dans le vrac.",
            "success",
        )
    else:
        flash(
            "Aucune pièce du vrac ne correspond aux pièces manquantes de ce set.",
            "error",
        )
    if return_to == "verify":
        with db.database() as connection:
            set_row = connection.execute(
                "SELECT set_num FROM sets WHERE id = ?", (set_id,)
            ).fetchone()
        if set_row is not None and set_row["set_num"]:
            return redirect(url_for("verify_set_page", set_num=set_row["set_num"]))
        return redirect(url_for("inventory_page"))
    if return_to == "pieces":
        return redirect(url_for("pieces_page"))
    return redirect(url_for("inventory_page"))



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
    with db.database() as connection:
        previous = connection.execute(
            "SELECT missing_quantity FROM set_parts WHERE id = ?", (part_id,)
        ).fetchone()
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
        if cursor.rowcount and previous:
            inventory.sync_minifig_components_from_parent(
                connection, part_id, previous["missing_quantity"]
            )
        if cursor.rowcount == 0:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Cette pièce n'existe plus."}), 404
            flash("Cette pièce n'existe plus.", "error")
        elif request.headers.get("X-Requested-With") == "XMLHttpRequest":
            part = connection.execute(
                """
                SELECT p.missing_quantity, p.quantity, p.part_num, p.color_id, p.set_id, p.item_type
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
            if part["item_type"] == "minifig":
                response_data["components"] = [
                    dict(row)
                    for row in connection.execute(
                        """
                        SELECT id, missing_quantity
                        FROM minifig_parts WHERE set_id = ? AND fig_num = ?
                        """,
                        (part["set_id"], part["part_num"]),
                    )
                ]
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



@app.post("/minifig-parts/<int:part_id>/status")
def update_minifig_part_status(part_id):
    status = request.form.get("status")
    change = request.form.get("change")
    mark_complete = request.form.get("mark_complete") == "1"
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not (
        (status in {"found", "missing"} and change is None and not mark_complete)
        or (change in {"-1", "1"} and status is None and not mark_complete)
        or (mark_complete and status is None and change is None)
    ):
        message = "La modification de la pièce est invalide."
        if is_ajax:
            return jsonify({"error": message}), 400
        flash(message, "error")
        return redirect(url_for("pieces_page"))

    with db.database() as connection:
        part = connection.execute(
            """
            SELECT mp.id, mp.set_id, mp.fig_num, mp.part_name, mp.missing_quantity,
                   mp.quantity * p.quantity AS quantity
            FROM minifig_parts mp
            JOIN set_parts p ON p.set_id = mp.set_id AND p.part_num = mp.fig_num
                AND p.item_type = 'minifig'
            WHERE mp.id = ?
            """,
            (part_id,),
        ).fetchone()
        if part is not None:
            if change is not None:
                missing = min(part["quantity"], max(0, part["missing_quantity"] + int(change)))
            elif status == "missing":
                missing = part["quantity"]
            else:
                missing = 0
            connection.execute(
                "UPDATE minifig_parts SET missing_quantity = ? WHERE id = ?",
                (missing, part_id),
            )
            inventory.sync_minifig_parent_from_components(connection, part["set_id"], part["fig_num"])
            gathering_cursor = connection.execute(
                """
                UPDATE sets SET in_gathering = 0
                WHERE id = ? AND in_collection = 1 AND in_gathering = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM set_parts
                      WHERE set_id = sets.id AND missing_quantity > 0
                  )
                """,
                (part["set_id"],),
            )
            parent = connection.execute(
                """
                SELECT id, part_num, color_id, quantity, missing_quantity
                FROM set_parts
                WHERE set_id = ? AND part_num = ? AND item_type = 'minifig'
                """,
                (part["set_id"], part["fig_num"]),
            ).fetchone()
            part_missing = connection.execute(
                """
                SELECT COALESCE(SUM(p.missing_quantity), 0)
                FROM sets s JOIN set_parts p ON p.set_id = s.id
                WHERE s.in_gathering = 1 AND p.part_num = ? AND p.color_id = ?
                """,
                (parent["part_num"], parent["color_id"]),
            ).fetchone()[0]
            set_missing = connection.execute(
                "SELECT COALESCE(SUM(missing_quantity), 0) FROM set_parts WHERE set_id = ?",
                (part["set_id"],),
            ).fetchone()[0]

    if part is None:
        message = "Cette pièce de figurine n'existe plus."
        if is_ajax:
            return jsonify({"error": message}), 404
        flash(message, "error")
        return redirect(url_for("pieces_page"))
    if is_ajax:
        return jsonify(
            {
                "part_name": part["part_name"],
                "quantity": part["quantity"],
                "missing_quantity": missing,
                "parent_id": parent["id"],
                "missing": parent["missing_quantity"],
                "parent_quantity": parent["quantity"],
                "part_missing": part_missing,
                "set_id": part["set_id"],
                "set_missing": set_missing,
                "gathering_complete": gathering_cursor.rowcount > 0,
            }
        )
    flash("Statut de la pièce de figurine mis à jour.", "success")
    return redirect(url_for("pieces_page"))
