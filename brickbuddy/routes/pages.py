"""Écrans : accueil, pièces, sets, inventaire, manquantes, vérification, paramètres."""
from .. import auth
from .. import colors
from .. import dashboard
from .. import db
from .. import inventory
from .. import prices
from .. import rates
from .. import rebrickable
from .. import settings
from ..flask_app import app
from flask import abort, flash, jsonify, redirect, render_template, request, url_for
import os
import re
import sqlite3

@app.get("/")
def index():
    # L'accueil est la page d'entrée de l'app : c'est là que le taux du jour est relevé.
    rates.request_rate_refresh()
    return render_template(
        "dashboard.html",
        summary=dashboard.collection_summary(),
        show_prices=prices.prices_enabled(),
    )



@app.get("/health")
def health():
    try:
        with db.database() as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error:
        app.logger.exception("Health check failed while accessing the database")
        return jsonify(status="unhealthy"), 503
    return jsonify(status="ok")



@app.get("/pieces")
def pieces_page():
    search = request.args.get("q", "").strip()
    color_filter = request.args.get("color", "").strip()
    sort_by = request.args.get("sort", "color")
    groups, menu_colors, parts = inventory.get_piece_groups(
        search, color_filter, sort_by, gathering_only=True
    )
    copy_state = "in_gathering"
    with db.database() as connection:
        sets_to_assemble = [
            dict(row)
            for row in connection.execute(
                """
                SELECT s.id, s.set_num, s.title, s.set_image_url, s.year, s.theme_name,
                       s.in_collection,
                       (SELECT COUNT(*) FROM sets other
                        WHERE other.set_num = s.set_num AND other.id <= s.id
                          AND other.{copy_state} = 1) AS copy_number,
                       (SELECT COUNT(*) FROM sets other
                        WHERE other.set_num = s.set_num
                          AND other.{copy_state} = 1) AS copy_count,
                       COALESCE(SUM(p.quantity), 0) AS total,
                       COALESCE(SUM(p.missing_quantity), 0) AS missing,
                       COUNT(p.id) AS part_count
                FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
                WHERE s.in_gathering = 1
                GROUP BY s.id
                ORDER BY s.created_at DESC, s.set_num
                """.format(copy_state=copy_state)
            ).fetchall()
        ]
    return render_template(
        "pieces.html",
        groups=groups,
        group_columns=inventory.split_color_groups(groups),
        colors=menu_colors,
        parts=parts,
        search=search,
        color_filter=colors.official_color_name(color_filter),
        sort_by=sort_by,
        sets_to_assemble=sets_to_assemble,
        has_api_key=bool(settings.setting_value("REBRICKABLE_API_KEY")),
        minifig_parts_by_set=inventory.get_gathering_minifig_parts_map(),
    )



@app.get("/sets")
def sets_page():
    search = request.args.get("q", "").strip()
    copy_state = "in_collection"
    params = []
    sql = """
        SELECT s.id AS set_id, s.set_num, s.title, s.set_image_url, s.year,
               s.theme_name, s.in_gathering,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num AND other.id <= s.id
                  AND other.{copy_state} = 1) AS copy_number,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num
                  AND other.{copy_state} = 1) AS copy_count,
               p.id AS part_id, p.part_num, p.part_name, p.color_id,
               p.color_name, p.quantity, p.missing_quantity, p.image_url
        FROM sets s LEFT JOIN set_parts p ON p.set_id = s.id
        WHERE s.in_collection = 1
    """.format(copy_state=copy_state)
    if search:
        sql += " AND (s.set_num LIKE ? OR s.title LIKE ?)"
        params.extend([f"%{search}%"] * 2)
    sql += " ORDER BY s.created_at DESC, s.set_num, p.part_name, p.color_name"
    with db.database() as connection:
        rows = connection.execute(sql, params).fetchall()
        # Les notices sont partagees par reference : un comptage pour tous les exemplaires.
        instruction_counts = {
            row["set_num"]: row["total"]
            for row in connection.execute(
                "SELECT set_num, COUNT(*) AS total FROM set_instructions GROUP BY set_num"
            ).fetchall()
        }
    sets = {}
    for row in rows:
        item = sets.setdefault(
            row["set_id"],
            {
                "id": row["set_id"],
                "set_num": row["set_num"],
                "copy_number": row["copy_number"],
                "copy_count": row["copy_count"],
                "title": row["title"],
                "set_image_url": row["set_image_url"],
                "year": row["year"],
                "theme_name": row["theme_name"],
                "parts": [],
                "total": 0,
                "missing": 0,
            },
        )
        if row["part_id"] is not None:
            part = dict(row)
            # Graphies multiples d'une même couleur : une seule carte dans la liste du set.
            part["color_label"] = colors.color_group_label(part["color_name"])
            part["color_key"] = colors.color_group_key(part["color_name"])
            item["parts"].append(part)
            item["total"] += part["quantity"]
            item["missing"] += part["missing_quantity"]
    theme_groups = {}
    for set_item in sets.values():
        set_item["instruction_count"] = instruction_counts.get(set_item["set_num"], 0)
        theme_groups.setdefault(set_item["theme_name"], []).append(set_item)
    return render_template(
        "sets.html",
        theme_groups=[
            {"name": name, "sets": theme_sets}
            for name, theme_sets in sorted(
                theme_groups.items(),
                key=lambda item: (
                    item[0] == "Thème non renseigné",
                    item[0].casefold(),
                ),
            )
        ],
        set_count=len(sets),
        search=search,
        has_api_key=bool(settings.setting_value("REBRICKABLE_API_KEY")),
        minifig_parts=inventory.get_minifig_parts_map(),
    )



@app.get("/inventaire")
def inventory_page():
    prices.request_price_refresh()
    search = request.args.get("q", "").strip()
    color_filter = request.args.get("color", "").strip()
    # Le filtre est comparé sur le nom officiel : « rouge » trouve les pièces « Red ».
    color_key = colors.color_group_key(color_filter) if color_filter else ""
    origin_filter = request.args.get("origin", "all").strip()
    if origin_filter not in {"all", "stock", "sets", "reserved", "mixed"}:
        origin_filter = "all"

    with db.database() as connection:
        owned = inventory.get_owned_parts(connection)

        matched_keys = set()
        if search:
            like = f"%{search}%"
            matched_keys = {
                (row["part_num"], int(row["color_id"] or 0))
                for row in connection.execute(
                    """
                    SELECT DISTINCT p.part_num, p.color_id
                    FROM sets s JOIN set_parts p ON p.set_id = s.id
                    WHERE s.set_num LIKE ? OR s.title LIKE ?
                    """,
                    (like, like),
                ).fetchall()
            }

        # Une couleur saisie en français et une couleur Rebrickable sont la même ligne de menu.
        stock_colors = {}
        for row in connection.execute(
            """
            SELECT color_id, color_name FROM stock_parts
            UNION
            SELECT color_id, color_name FROM set_parts
            """
        ).fetchall():
            entry = stock_colors.setdefault(
                colors.color_group_key(row["color_name"]),
                {
                    "color_id": int(row["color_id"] or 0),
                    "color_name": colors.official_color_name(row["color_name"]),
                    "label": colors.color_group_label(row["color_name"]),
                },
            )
            # Un color_id connu prend le dessus sur une saisie manuelle sans identifiant.
            if not entry["color_id"] and row["color_id"]:
                entry["color_id"] = int(row["color_id"])
        stock_color_options = sorted(
            stock_colors.values(),
            key=lambda option: (option["label"].casefold(), option["color_id"]),
        )

    def matches_origin(part):
        if origin_filter == "stock":
            return part["stock_qty"] > 0
        if origin_filter == "sets":
            return part["set_qty"] > 0
        if origin_filter == "reserved":
            return part["reserved_qty"] > 0
        if origin_filter == "mixed":
            return (
                sum(
                    1
                    for quantity in (
                        part["stock_qty"],
                        part["set_qty"],
                        part["reserved_qty"],
                    )
                    if quantity > 0
                )
                >= 2
            )
        return True

    needle = search.casefold()
    parts = []
    for part in owned.values():
        if not matches_origin(part):
            continue
        if needle:
            haystack = " ".join(
                (
                    part["part_num"],
                    part["part_name"] or "",
                    *colors.search_terms(part["color_name"]),
                )
            ).casefold()
            if needle not in haystack and (part["part_num"], part["color_id"]) not in matched_keys:
                continue
        if color_key and colors.color_group_key(part["color_name"]) != color_key:
            continue
        part["color_label"] = colors.color_group_label(part["color_name"])
        parts.append(part)

    # Une couleur enregistrée sous deux graphies (Rebrickable, saisie manuelle) fait une seule carte.
    color_groups = {}
    for part in parts:
        group = color_groups.setdefault(
            colors.color_group_key(part["color_name"]),
            {"name": part["color_label"], "parts": [], "quantity": 0},
        )
        group["parts"].append(part)
        group["quantity"] += part["total"]

    groups = sorted(
        color_groups.values(),
        key=lambda group: (group["name"] == "Figurine", group["name"].casefold()),
    )

    menu_colors = colors.color_options(
        {part["color_name"] for part in owned.values()}
    )

    return render_template(
        "inventory.html",
        groups=groups,
        colors=menu_colors,
        color_filter=colors.official_color_name(color_filter),
        search=search,
        origin_filter=origin_filter,
        total_quantity=sum(part["total"] for part in parts),
        stock_quantity=sum(part["stock_qty"] for part in parts),
        set_quantity=sum(part["set_qty"] for part in parts),
        reserved_quantity=sum(part["reserved_qty"] for part in parts),
        part_count=len(parts),
        stock_color_options=stock_color_options,
        minifig_parts=inventory.get_minifig_parts_map(),
        show_prices=prices.prices_enabled(),
        total_price=round(
            sum(part["line_total"] for part in parts if part["line_total"]), 2
        ),
        priced_part_count=sum(1 for part in parts if part["line_total"]),
        price_refresh_date=prices.price_refresh_date() if prices.prices_enabled() else "",
        price_refresh_running=prices.price_refresh_running(),
    )



@app.get("/inventaire/verifier")
def verify_set_page():
    raw_set_num = request.args.get("set_num", "").strip()
    context = {
        "set_num": raw_set_num,
        "rows": [],
        "summary": None,
        "error": None,
        "existing_set_id": None,
        "has_api_key": bool(settings.setting_value("REBRICKABLE_API_KEY")),
        "set_info": None,
        "checked": False,
        "minifig_parts": inventory.get_minifig_parts_map(),
    }
    if not raw_set_num:
        return render_template("verify_set.html", **context)

    set_num = raw_set_num
    if "-" not in set_num:
        set_num = f"{set_num}-1"
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", set_num):
        context["error"] = f"Numéro de set invalide : {raw_set_num}."
        return render_template("verify_set.html", **context)

    context["set_num"] = set_num
    if not context["has_api_key"]:
        context["error"] = "Configurez REBRICKABLE_API_KEY pour vérifier un set."
        return render_template("verify_set.html", **context)

    try:
        set_info, api_parts = rebrickable.fetch_set_inventory(set_num)
    except (RuntimeError, ValueError) as error:
        context["error"] = str(error)
        return render_template("verify_set.html", **context)

    with db.database() as connection:
        owned = inventory.get_owned_parts(connection)
        stock = {key: part["stock_qty"] for key, part in owned.items()}
        in_sets = {
            key: part["set_qty"] + part["reserved_qty"]
            for key, part in owned.items()
        }
        existing_row = connection.execute(
            """
            SELECT id FROM sets
            WHERE set_num = ? AND in_gathering = 1
            ORDER BY id LIMIT 1
            """,
            (set_num,),
        ).fetchone()

    rows = []
    for part in api_parts:
        needed = int(part.get("quantity") or 0)
        if needed <= 0:
            continue
        key = (str(part.get("part_num") or ""), int(part.get("color_id") or 0))
        stock_qty = stock.get(key, 0)
        sets_qty = in_sets.get(key, 0)
        take = min(needed, stock_qty)
        from_sets = min(sets_qty, needed - take)
        to_buy = max(0, needed - stock_qty - sets_qty)
        rows.append(
            {
                "part_num": part.get("part_num") or "",
                "part_name": part.get("part_name") or part.get("part_num") or "",
                "color_id": key[1],
                "color_name": part.get("color_name") or "Unknown",
                "item_type": part.get("item_type") or "part",
                "image_url": part.get("image_url") or "",
                "needed": needed,
                "stock": stock_qty,
                "in_sets": from_sets,
                "take": take,
                "to_buy": to_buy,
            }
        )
    rows.sort(
        key=lambda row: (row["color_name"].casefold(), row["part_name"].casefold())
    )

    summary = {
        "needed": sum(row["needed"] for row in rows),
        "from_stock": sum(row["take"] for row in rows),
        "from_sets": sum(row["in_sets"] for row in rows),
        "to_buy": sum(row["to_buy"] for row in rows),
    }
    summary["complete"] = summary["to_buy"] == 0

    context.update(
        rows=rows,
        summary=summary,
        set_info=set_info,
        existing_set_id=existing_row["id"] if existing_row else None,
        checked=True,
    )
    return render_template("verify_set.html", **context)



@app.get("/manquantes")
def missing_page():
    search = request.args.get("q", "").strip()
    color_filter = request.args.get("color", "").strip()
    sort_by = request.args.get("sort", "color")
    groups, menu_colors, parts = inventory.get_piece_groups(
        search, color_filter, sort_by, missing_only=True, owned_only=True
    )
    return render_template(
        "missing.html",
        groups=groups,
        group_columns=inventory.split_color_groups(groups),
        colors=menu_colors,
        parts=parts,
        search=search,
        color_filter=colors.official_color_name(color_filter),
        sort_by=sort_by,
        minifig_parts=inventory.get_minifig_parts_map(),
    )


@app.get("/parametres")
def settings_page():
    price_info = None
    if prices.prices_enabled():
        with db.database() as connection:
            owned = inventory.get_owned_parts(connection)
        price_info = {
            "covered": sum(1 for part in owned.values() if part["line_total"]),
            "total": len(owned),
            "date": prices.price_refresh_date(),
            "running": prices.price_refresh_running(),
        }
    return render_template(
        "settings.html",
        saved_names=[name for name in settings.SETTING_FIELDS if settings.setting(name)],
        env_names=[name for name in settings.SETTING_FIELDS if os.environ.get(name, "").strip()],
        show_prices=settings.flag("SHOW_PRICES"),
        price_info=price_info,
        rate_text=rates.format_rate(rates.current_rate()),
        rate_date=rates.rate_refresh_date(),
        rate_running=rates.rate_refresh_running(),
    )


@app.post("/parametres")
def settings_update():
    if not auth.form_csrf_ok():
        abort(400)
    values = {name: request.form.get(name, "") for name in settings.SETTING_FIELDS}
    values["SHOW_PRICES"] = request.form.get("SHOW_PRICES") == "on"
    settings.save_settings(values)
    # Le journal ne garde que les noms des options : une clé reste un secret.
    touched = [name for name in settings.SETTING_FIELDS if name in request.form]
    app.logger.info("Paramètres : options mises à jour · %s", " · ".join(touched))
    return redirect(url_for("settings_page"))


@app.post("/parametres/taux")
def settings_refresh_rate():
    if not auth.form_csrf_ok():
        abort(400)
    if rates.rate_refresh_running():
        flash("Un relevé du taux est déjà en cours, patientez un instant.", "error")
        return redirect(url_for("settings_page"))
    rate = rates.refresh_now()
    if rate:
        flash(f"Taux mis à jour : {rates.format_rate(rate)} € pour 1 £.", "success")
    else:
        flash("Le service de change n'a pas répondu : le taux connu est conservé.", "error")
    return redirect(url_for("settings_page"))
