"""Sets : ajout, collecte, duplication, vente, suppression."""
from .. import db
from .. import inventory
from .. import prices
from .. import rebrickable
from .. import settings
from ..flask_app import app
from flask import flash, redirect, request, url_for
import re

@app.post("/sets")
def add_set():
    add_to_collection = request.form.get("return_to") == "sets"
    all_parts_found = add_to_collection and request.form.get("all_parts_found") == "1"
    destination = "sets_page" if add_to_collection else "pieces_page"
    raw_number = request.form.get("set_num", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", raw_number):
        flash("Entrez une référence de set valide, par exemple 10312 ou 10312-1.", "error")
        return redirect(url_for(destination))
    set_num = raw_number if "-" in raw_number else f"{raw_number}-1"
    title = request.form.get("title", "").strip()
    theme_name = request.form.get("theme_name", "").strip() or "Thème non renseigné"
    set_image_url = ""
    year = None
    parts = []
    theme_warning = ""
    if settings.setting_value("REBRICKABLE_API_KEY"):
        try:
            set_info, parts = rebrickable.fetch_set_inventory(set_num)
            title = set_info.get("name") or title or f"Set {set_num}"
            set_image_url = set_info.get("set_img_url") or ""
            year = set_info.get("year")
            if set_info.get("theme_id"):
                try:
                    theme_name = rebrickable.fetch_theme_name(set_info["theme_id"])
                except (RuntimeError, ValueError) as error:
                    theme_name = f"Thème {set_info['theme_id']}"
                    theme_warning = (
                        f"Le thème n'a pas pu être récupéré depuis Rebrickable : {error}"
                    )
        except (RuntimeError, ValueError) as error:
            flash(str(error), "error")
            return redirect(url_for(destination))
    else:
        title = title or f"Set {set_num}"

    minifig_rows = []
    if settings.setting_value("REBRICKABLE_API_KEY"):
        try:
            minifig_rows = rebrickable.fetch_minifig_parts_for_set(set_num)
        except (RuntimeError, ValueError):
            minifig_rows = []

    with db.database() as connection:
        cursor = connection.execute(
            """
            INSERT INTO sets
                (set_num, title, set_image_url, theme_name, year, in_collection, in_gathering, all_parts_found)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                set_num,
                title,
                set_image_url,
                theme_name,
                year,
                int(add_to_collection),
                int(not add_to_collection),
                int(all_parts_found),
            ),
        )
        set_id = cursor.lastrowid
        imported_parts = [
            dict(
                part,
                set_id=set_id,
                missing_quantity=0 if all_parts_found else part["quantity"],
                item_type=part.get("item_type", "part"),
            )
            for part in parts
        ]
        connection.executemany(
            """
            INSERT INTO set_parts
                (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity, image_url, item_type)
            VALUES
                (:set_id, :part_num, :part_name, :color_id, :color_name, :quantity, :missing_quantity, :image_url, :item_type)
            """,
            imported_parts,
        )
        prices.remember_brickowl_boids(connection, imported_parts)
        if minifig_rows:
            inventory.replace_set_minifig_parts(
                connection,
                set_id,
                minifig_rows,
                all_parts_found=all_parts_found,
            )

    if parts:
        message = f"{title} ajouté avec {len(parts)} références de pièces importées."
        if all_parts_found:
            message += " Toutes les pièces sont marquées comme trouvées."
        flash(message, "success")
    elif settings.setting_value("REBRICKABLE_API_KEY"):
        flash(f"{title} ajouté. Aucun élément n'a été retourné par Rebrickable.", "success")
    else:
        flash(
            f"{title} ajouté. Ajoutez ses pièces manuellement"
            + ("" if add_to_collection else ", ou configurez Rebrickable pour les importer automatiquement")
            + ".",
            "success",
        )
    if theme_warning:
        flash(theme_warning, "error")
    return redirect(url_for(destination))



@app.post("/sets/<int:set_id>/collect")
def collect_set(set_id):
    with db.database() as connection:
        set_row = connection.execute(
            """
            SELECT s.in_collection, COUNT(p.id) AS part_count,
                   COALESCE(SUM(p.missing_quantity), 0) AS missing
            FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
            WHERE s.id = ?
            GROUP BY s.id
            """,
            (set_id,),
        ).fetchone()
        if not set_row or not set_row["part_count"]:
            flash("Ajoutez d'abord les pièces du set avant de le valider.", "error")
            return redirect(url_for("pieces_page"))
        cursor = connection.execute(
            """
            UPDATE sets
            SET in_collection = 1,
                in_gathering = CASE WHEN ? = 0 THEN 0 ELSE in_gathering END
            WHERE id = ? AND in_collection = 0
            """,
            (set_row["missing"], set_id),
        )
    if cursor.rowcount:
        flash(
            "Set ajouté à Mes sets."
            + (" Toutes ses pièces sont déjà trouvées ; il est retiré de À réunir." if not set_row["missing"] else ""),
            "success",
        )
    else:
        flash("Ce set n'existe plus ou figure déjà dans Mes sets.", "error")
    return redirect(url_for("pieces_page"))



@app.post("/sets/<int:set_id>/gathering")
def update_set_gathering(set_id):
    gathering = request.form.get("in_gathering")
    destination = "pieces_page" if request.form.get("return_to") == "pieces" else "sets_page"
    if gathering not in {"0", "1"}:
        flash("État de recherche invalide.", "error")
        return redirect(url_for(destination))
    with db.database() as connection:
        cursor = connection.execute(
            """
            UPDATE sets
            SET in_gathering = ?,
                all_parts_found = CASE WHEN ? = 1 THEN 0 ELSE all_parts_found END
            WHERE id = ?
            """,
            (int(gathering), int(gathering), set_id),
        )
        removed = cursor.rowcount and _delete_untracked_set(connection, set_id)
    if removed:
        flash(
            "Ce set n'était ni dans Mes sets ni en recherche : il a été retiré"
            " avec ses pièces.",
            "success",
        )
    elif cursor.rowcount:
        message = (
            "Les pièces de ce set sont ajoutées à À réunir."
            if gathering == "1"
            else "Les pièces de ce set sont retirées de À réunir."
        )
        flash(message, "success")
    else:
        flash("Ce set n'existe plus.", "error")
    return redirect(url_for(destination))



@app.post("/sets/<int:set_id>/duplicate")
def duplicate_set(set_id):
    destination = request.form.get("return_to")
    if destination not in {"pieces", "sets"}:
        flash("Destination de l'exemplaire invalide.", "error")
        return redirect(url_for("pieces_page"))

    copy_state = "in_gathering" if destination == "pieces" else "in_collection"
    with db.database() as connection:
        source = connection.execute(
            f"""
            SELECT set_num, title, set_image_url, theme_name, year
            FROM sets WHERE id = ? AND {copy_state} = 1
            """,
            (set_id,),
        ).fetchone()
        if source is None:
            flash("Ce set n'existe plus dans cette liste.", "error")
            return redirect(url_for("pieces_page" if destination == "pieces" else "sets_page"))

        cursor = connection.execute(
            """
            INSERT INTO sets
                (set_num, title, set_image_url, theme_name, year,
                 in_collection, in_gathering, all_parts_found)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                source["set_num"],
                source["title"],
                source["set_image_url"],
                source["theme_name"],
                source["year"],
                int(destination == "sets"),
                int(destination == "pieces"),
            ),
        )
        new_set_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO set_parts
                (set_id, part_num, part_name, color_id, color_name,
                 quantity, missing_quantity, image_url, item_type)
            SELECT ?, part_num, part_name, color_id, color_name,
                   quantity, quantity, image_url, item_type
            FROM set_parts WHERE set_id = ?
            """,
            (new_set_id, set_id),
        )
        connection.execute(
            """
            INSERT INTO minifig_parts
                (set_id, fig_num, part_num, part_name, color_id, color_name,
                 quantity, missing_quantity, image_url)
            SELECT ?, mp.fig_num, mp.part_num, mp.part_name, mp.color_id, mp.color_name,
                   mp.quantity, mp.quantity * COALESCE(p.quantity, 1), mp.image_url
            FROM minifig_parts mp
            LEFT JOIN set_parts p ON p.set_id = mp.set_id
                AND p.part_num = mp.fig_num AND p.item_type = 'minifig'
            WHERE mp.set_id = ?
            """,
            (new_set_id, set_id),
        )

    flash(
        f"Nouvel exemplaire de {source['title']} ajouté ; ses pièces sont à vérifier.",
        "success",
    )
    return redirect(url_for("pieces_page" if destination == "pieces" else "sets_page"))



@app.post("/sets/<int:set_id>/complete-parts")
def complete_set_parts(set_id):
    with db.database() as connection:
        set_row = connection.execute(
            """
            SELECT s.title, COALESCE(SUM(p.missing_quantity), 0) AS missing
            FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
            WHERE s.id = ?
            GROUP BY s.id
            """,
            (set_id,),
        ).fetchone()
        if set_row is None:
            flash("Ce set n'existe plus.", "error")
            return redirect(url_for("pieces_page"))
        part_count = connection.execute(
            "SELECT COUNT(*) FROM set_parts WHERE set_id = ?", (set_id,)
        ).fetchone()[0]
        if not part_count:
            flash("Ajoutez d'abord les pièces du set avant de le compléter.", "error")
            return redirect(url_for("pieces_page"))
        if set_row["missing"]:
            connection.execute(
                "UPDATE set_parts SET missing_quantity = 0 WHERE set_id = ?",
                (set_id,),
            )
            connection.execute(
                "UPDATE minifig_parts SET missing_quantity = 0 WHERE set_id = ?",
                (set_id,),
            )
            connection.execute(
                "UPDATE sets SET in_gathering = 0 WHERE id = ? AND in_collection = 1",
                (set_id,),
            )
            message = f"Toutes les pièces de {set_row['title']} sont marquées comme trouvées."
        else:
            connection.execute(
                "UPDATE set_parts SET missing_quantity = quantity WHERE set_id = ?",
                (set_id,),
            )
            connection.execute(
                """
                UPDATE minifig_parts
                SET missing_quantity = quantity * COALESCE(
                    (SELECT p.quantity FROM set_parts p
                     WHERE p.set_id = minifig_parts.set_id
                       AND p.part_num = minifig_parts.fig_num
                       AND p.item_type = 'minifig'), 1)
                WHERE set_id = ?
                """,
                (set_id,),
            )
            connection.execute(
                "UPDATE sets SET in_gathering = 1, all_parts_found = 0 WHERE id = ?",
                (set_id,),
            )
            message = f"Toutes les pièces de {set_row['title']} sont à nouveau à chercher."
    flash(message, "success")
    destination = "sets_page" if request.form.get("return_to") == "sets" else "pieces_page"
    return redirect(url_for(destination))



@app.post("/sets/<int:set_id>/uncollect")
def uncollect_set(set_id):
    with db.database() as connection:
        cursor = connection.execute(
            "UPDATE sets SET in_collection = 0 WHERE id = ? AND in_collection = 1",
            (set_id,),
        )
        removed = cursor.rowcount and _delete_untracked_set(connection, set_id)
    if removed:
        flash(
            "Ce set n'était plus en recherche : il a été retiré avec ses pièces.",
            "success",
        )
    elif cursor.rowcount:
        flash("Set retiré de Mes sets. Le suivi de ses pièces reste inchangé.", "success")
    else:
        flash("Ce set n'existe plus ou n'est pas dans Mes sets.", "error")
    return redirect(url_for("sets_page"))



@app.post("/sets/<int:set_id>/sold")
def sell_set(set_id):
    """Un exemplaire vendu ne figure sur aucun écran : on le retire avec ses pièces."""
    with db.database() as connection:
        set_row = connection.execute(
            "SELECT title FROM sets WHERE id = ? AND in_collection = 1",
            (set_id,),
        ).fetchone()
        if set_row is not None:
            connection.execute("DELETE FROM set_parts WHERE set_id = ?", (set_id,))
            connection.execute("DELETE FROM minifig_parts WHERE set_id = ?", (set_id,))
            connection.execute("DELETE FROM sets WHERE id = ?", (set_id,))
    if set_row is not None:
        flash(
            f"{set_row['title']} retiré de Mes sets ; ses pièces ne comptent plus"
            " dans ton inventaire.",
            "success",
        )
    else:
        flash("Ce set n'existe plus dans Mes sets.", "error")
    return redirect(url_for("sets_page"))



@app.post("/sets/<int:set_id>/parts")
def add_part(set_id):
    part_num = request.form.get("part_num", "").strip()
    part_name = request.form.get("part_name", "").strip() or part_num
    color_name = request.form.get("color_name", "").strip() or "Unknown"
    try:
        quantity = int(request.form.get("quantity", "1"))
        color_id = int(request.form.get("color_id", "0") or 0)
        if not part_num or quantity < 1 or color_id < 0:
            raise ValueError
    except ValueError:
        flash("Vérifiez la référence, la couleur et la quantité de la pièce.", "error")
        return redirect(url_for(_set_return_endpoint()))

    with db.database() as connection:
        set_row = connection.execute(
            "SELECT id, all_parts_found FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
        if not set_row:
            flash("Ce set n'existe plus.", "error")
            return redirect(url_for(_set_return_endpoint()))
        missing_quantity = 0 if set_row["all_parts_found"] else quantity
        connection.execute(
            """
            INSERT INTO set_parts
                (set_id, part_num, part_name, color_id, color_name, quantity, missing_quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(set_id, part_num, color_id) DO UPDATE SET
                quantity = quantity + excluded.quantity,
                missing_quantity = missing_quantity + excluded.missing_quantity,
                part_name = excluded.part_name,
                color_name = excluded.color_name
            """,
            (
                set_id,
                part_num,
                part_name,
                color_id,
                color_name,
                quantity,
                missing_quantity,
            ),
        )
    flash(f"Pièce {part_num} ajoutée.", "success")
    return redirect(url_for(_set_return_endpoint()))



def _set_return_endpoint():
    return {
        "pieces": "pieces_page",
        "sets": "sets_page",
    }.get(request.form.get("return_to"), "pieces_page")


def _delete_untracked_set(connection, set_id):
    """Retire un set que plus aucun écran n'affiche, avec ses pièces.

    Un set sans écran (ni « Mes sets », ni « Pièces à réunir ») reste en base
    sans jamais être visible ni accessible : ses lignes sont des déchets. Les
    pièces sont supprimées explicitement, sans compter sur la cascade, pour que
    ce nettoyage fonctionne aussi sur les bases anciennes dont le schéma ne la
    déclarait pas. Les notices sont gardées : elles sont partagées par
    référence et un set réajouté les retrouve.
    """
    untracked = connection.execute(
        """
        SELECT id FROM sets
        WHERE id = ? AND in_collection = 0 AND in_gathering = 0
        """,
        (set_id,),
    ).fetchone()
    if untracked is None:
        return False
    connection.execute("DELETE FROM set_parts WHERE set_id = ?", (set_id,))
    connection.execute("DELETE FROM minifig_parts WHERE set_id = ?", (set_id,))
    connection.execute("DELETE FROM sets WHERE id = ?", (set_id,))
    return True


@app.post("/sets/<int:set_id>/delete")
def delete_set(set_id):
    with db.database() as connection:
        connection.execute("DELETE FROM set_parts WHERE set_id = ?", (set_id,))
        connection.execute("DELETE FROM minifig_parts WHERE set_id = ?", (set_id,))
        connection.execute("DELETE FROM sets WHERE id = ?", (set_id,))
    flash("Set supprimé de la liste à réunir ou de Mes sets.", "success")
    destination = {
        "pieces": "pieces_page",
        "sets": "sets_page",
    }.get(request.form.get("return_to"), "sets_page")
    return redirect(url_for(destination))
