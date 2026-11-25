"""Lecture de l'inventaire : pièces possédées, figurines, groupes."""
from . import colors
from . import db
from . import prices
from flask import jsonify, render_template

def get_minifig_parts_map():
    """Composition des figurines, agrégée par (fig_num, part_num, color_id)."""
    with db.database() as connection:
        rows = connection.execute(
            """
            SELECT fig_num, part_num, part_name, color_id, color_name,
                   MAX(quantity) AS quantity, MAX(image_url) AS image_url
            FROM minifig_parts
            GROUP BY fig_num, part_num, color_id
            ORDER BY fig_num, color_name COLLATE NOCASE,
                     part_name COLLATE NOCASE
            """
        ).fetchall()
    mapping = {}
    for row in rows:
        mapping.setdefault(row["fig_num"], []).append(
            {
                "fig_num": row["fig_num"],
                "part_num": row["part_num"],
                "part_name": row["part_name"],
                "color_id": int(row["color_id"] or 0),
                "color_name": row["color_name"],
                "quantity": int(row["quantity"] or 0),
                "image_url": row["image_url"] or "",
            }
        )
    return mapping



def get_gathering_minifig_parts_map():
    with db.database() as connection:
        rows = connection.execute(
            """
            SELECT mp.id, mp.set_id, mp.fig_num, mp.part_num, mp.part_name,
                   mp.color_id, mp.color_name, mp.quantity * p.quantity AS quantity,
                   mp.missing_quantity,
                   mp.image_url
            FROM minifig_parts mp
            JOIN sets s ON s.id = mp.set_id
            JOIN set_parts p ON p.set_id = mp.set_id
                AND p.part_num = mp.fig_num AND p.item_type = 'minifig'
            WHERE s.in_gathering = 1
            ORDER BY mp.set_id, mp.fig_num, mp.color_name COLLATE NOCASE,
                     mp.part_name COLLATE NOCASE
            """
        ).fetchall()
    mapping = {}
    for row in rows:
        mapping.setdefault(row["set_id"], {}).setdefault(row["fig_num"], []).append(
            {
                "id": row["id"],
                "fig_num": row["fig_num"],
                "part_num": row["part_num"],
                "part_name": row["part_name"],
                "color_id": int(row["color_id"] or 0),
                "color_name": row["color_name"],
                "quantity": int(row["quantity"] or 0),
                "missing_quantity": int(row["missing_quantity"] or 0),
                "image_url": row["image_url"] or "",
            }
        )
    return mapping



def sync_minifig_components_from_parent(connection, part_id, previous_missing):
    parent = connection.execute(
        "SELECT set_id, part_num, item_type, missing_quantity FROM set_parts WHERE id = ?",
        (part_id,),
    ).fetchone()
    if not parent or parent["item_type"] != "minifig":
        return
    missing = parent["missing_quantity"]
    if missing == previous_missing:
        return
    connection.execute(
        """
        UPDATE minifig_parts
        SET missing_quantity = MAX(0, missing_quantity + quantity * ?)
        WHERE set_id = ? AND fig_num = ?
        """,
        (missing - previous_missing, parent["set_id"], parent["part_num"]),
    )



def sync_minifig_parent_from_components(connection, set_id, fig_num):
    connection.execute(
        """
        UPDATE set_parts
        SET missing_quantity = (
            SELECT MIN(set_parts.quantity, MAX(
                (mp.missing_quantity + mp.quantity - 1) / mp.quantity))
            FROM minifig_parts mp
            WHERE mp.set_id = set_parts.set_id AND mp.fig_num = set_parts.part_num
        )
        WHERE set_id = ? AND part_num = ? AND item_type = 'minifig'
          AND EXISTS (
              SELECT 1 FROM minifig_parts mp
              WHERE mp.set_id = set_parts.set_id AND mp.fig_num = set_parts.part_num
          )
        """,
        (set_id, fig_num),
    )



def replace_set_minifig_parts(
    connection, set_id, rows, all_parts_found=False, previous_figure_quantities=None
):
    previous_components = {
        (row["fig_num"], row["part_num"], row["color_id"]): row
        for row in connection.execute(
            """
            SELECT fig_num, part_num, color_id, quantity, missing_quantity
            FROM minifig_parts WHERE set_id = ?
            """,
            (set_id,),
        ).fetchall()
    }
    parents = {
        row["part_num"]: row
        for row in connection.execute(
            """
            SELECT part_num, quantity, missing_quantity FROM set_parts
            WHERE set_id = ? AND item_type = 'minifig'
            """,
            (set_id,),
        )
    }
    previous_figure_quantities = previous_figure_quantities or {
        fig_num: parent["quantity"] for fig_num, parent in parents.items()
    }
    components = []
    for row in rows:
        fig_num = row.get("fig_num") or ""
        part_num = row.get("part_num") or ""
        color_id = int(row.get("color_id") or 0)
        quantity = int(row.get("quantity") or 0)
        parent = parents.get(fig_num)
        figure_quantity = parent["quantity"] if parent else 1
        previous = previous_components.get((fig_num, part_num, color_id))
        if previous is not None:
            previous_total = previous["quantity"] * previous_figure_quantities.get(fig_num, 1)
            found = max(0, previous_total - previous["missing_quantity"])
            missing = max(0, quantity * figure_quantity - found)
        else:
            missing_figures = parent["missing_quantity"] if parent else (0 if all_parts_found else 1)
            missing = quantity * missing_figures
        components.append(
            {
                "set_id": set_id,
                "fig_num": fig_num,
                "part_num": part_num,
                "part_name": row.get("part_name") or part_num,
                "color_id": color_id,
                "color_name": row.get("color_name") or "Unknown",
                "quantity": quantity,
                "missing_quantity": missing,
                "image_url": row.get("image_url") or "",
            }
        )
    connection.execute("DELETE FROM minifig_parts WHERE set_id = ?", (set_id,))
    connection.executemany(
        """
        INSERT INTO minifig_parts
            (set_id, fig_num, part_num, part_name, color_id, color_name,
             quantity, missing_quantity, image_url)
        VALUES
            (:set_id, :fig_num, :part_num, :part_name, :color_id, :color_name,
             :quantity, :missing_quantity, :image_url)
        """,
        components,
    )
    for fig_num in {row.get("fig_num") or "" for row in rows}:
        sync_minifig_parent_from_components(connection, set_id, fig_num)



def get_owned_parts(connection):
    """Agrège toutes les pièces possédées, tous emplacements confondus.

    Le total possédé est toujours recalculé (jamais stocké) :
    total = vrac + pièces issues des sets en collection + pièces réservées
    (sets en préparation dont la pièce a été trouvée au moins en partie).
    """
    rows = connection.execute(
        """
        SELECT part_num, color_id,
               MAX(part_name) AS part_name,
               MAX(color_name) AS color_name,
               MAX(item_type) AS item_type,
               MAX(image_url) AS image_url,
               SUM(stock_qty) AS stock_qty,
               SUM(set_qty) AS set_qty,
               SUM(reserved_qty) AS reserved_qty
        FROM (
            SELECT sp.part_num, sp.color_id, sp.part_name, sp.color_name,
                   sp.item_type, sp.image_url,
                   sp.quantity AS stock_qty, 0 AS set_qty, 0 AS reserved_qty
            FROM stock_parts sp
            UNION ALL
            SELECT p.part_num, p.color_id, MAX(p.part_name), MAX(p.color_name),
                   MAX(p.item_type), MAX(p.image_url),
                   0, SUM(p.quantity - p.missing_quantity), 0
            FROM set_parts p JOIN sets s ON s.id = p.set_id
            WHERE s.in_collection = 1
            GROUP BY p.part_num, p.color_id
            UNION ALL
            SELECT p.part_num, p.color_id, MAX(p.part_name), MAX(p.color_name),
                   MAX(p.item_type), MAX(p.image_url),
                   0, 0, SUM(p.quantity - p.missing_quantity)
            FROM set_parts p JOIN sets s ON s.id = p.set_id
            WHERE s.in_gathering = 1 AND s.in_collection = 0
              AND p.missing_quantity < p.quantity
            GROUP BY p.part_num, p.color_id
        )
        GROUP BY part_num, color_id
        HAVING SUM(stock_qty) + SUM(set_qty) + SUM(reserved_qty) > 0
        ORDER BY color_name COLLATE NOCASE, part_name COLLATE NOCASE,
                 part_num, item_type
        """
    ).fetchall()

    reserved_set_nums = {}
    reserved_set_tones = {}
    for row in connection.execute(
        """
        SELECT p.part_num, p.color_id, s.set_num, s.id AS set_id
        FROM set_parts p JOIN sets s ON s.id = p.set_id
        WHERE s.in_gathering = 1 AND s.in_collection = 0
          AND p.missing_quantity < p.quantity
        ORDER BY s.set_num, s.id
        """
    ):
        key = (row["part_num"], int(row["color_id"]))
        reserved_set_nums.setdefault(key, []).append(row["set_num"])
        tones = reserved_set_tones.setdefault(key, [])
        tone = int(row["set_id"]) % 6
        if tone not in tones:
            tones.append(tone)

    collected_set_counts = {
        (row["part_num"], int(row["color_id"])): int(row["set_count"] or 0)
        for row in connection.execute(
            """
            SELECT p.part_num, p.color_id, COUNT(DISTINCT s.id) AS set_count
            FROM set_parts p JOIN sets s ON s.id = p.set_id
            WHERE s.in_collection = 1
              AND p.quantity > p.missing_quantity
            GROUP BY p.part_num, p.color_id
            """
        )
    }

    stock_ids = {
        (row["part_num"], int(row["color_id"])): row["id"]
        for row in connection.execute(
            "SELECT id, part_num, color_id FROM stock_parts"
        )
    }

    owned = {}
    for row in rows:
        key = (row["part_num"], int(row["color_id"] or 0))
        stock_qty = int(row["stock_qty"] or 0)
        set_qty = int(row["set_qty"] or 0)
        reserved_qty = int(row["reserved_qty"] or 0)
        total = stock_qty + set_qty + reserved_qty
        counter_count = sum(
            1 for quantity in (stock_qty, set_qty, reserved_qty) if quantity > 0
        )
        if counter_count == 1:
            if stock_qty > 0:
                origin = "stock"
            elif set_qty > 0:
                origin = "sets"
            else:
                origin = "reserved"
        else:
            origin = "mixed"

        badges = []
        if stock_qty > 0 and set_qty > 0:
            badges.append({"label": "Sets + vrac", "tone": "mixed"})
        elif stock_qty > 0:
            badges.append({"label": "En stock", "tone": "stock"})
        elif set_qty > 0:
            badges.append({"label": "Dans un set", "tone": "sets"})
        if reserved_qty > 0:
            set_nums = list(dict.fromkeys(reserved_set_nums.get(key, [])))
            label = "Réservé"
            if set_nums:
                label = f"Réservé · {', '.join(set_nums)}"
            tones = reserved_set_tones.get(key, [])
            badges.append(
                {
                    "label": label,
                    "tone": "reserved",
                    "set_tone": tones[0] if tones else None,
                }
            )

        owned[key] = {
            "part_num": row["part_num"],
            "color_id": int(row["color_id"] or 0),
            "part_name": row["part_name"],
            "color_name": row["color_name"],
            "item_type": row["item_type"] or "part",
            "image_url": row["image_url"] or "",
            "stock_qty": stock_qty,
            "set_qty": set_qty,
            "set_count": collected_set_counts.get(key, 0),
            "reserved_qty": reserved_qty,
            "reserved_set_count": len(
                dict.fromkeys(reserved_set_nums.get(key, []))
            ),
            "total": total,
            # Clé de compatibilité pour le rendu « ×{{ quantity }} ».
            "quantity": total,
            "origin": origin,
            "badges": badges,
            "stock_id": stock_ids.get(key),
        }

    price_map = prices.load_price_map(connection) if prices.prices_enabled() else {}
    for key, part in owned.items():
        unit_price = price_map.get(key)
        part["unit_price"] = unit_price
        part["line_total"] = round(unit_price * part["total"], 2) if unit_price else None
    return owned



def _stock_update_response(connection, part_num, color_id):
    """Réponse JSON d'une mise à jour du vrac : la carte d'inventaire re-rendue."""
    part = get_owned_parts(connection).get((part_num, int(color_id)))
    if part is None:
        return jsonify(
            {"removed": True, "html": "", "total": 0, "quantity": 0, "stock_id": None}
        )
    return jsonify(
        {
            "removed": False,
            "html": render_template(
                "_inventory_card.html",
                part=part,
                minifig_parts=get_minifig_parts_map(),
            ),
            "total": part["total"],
            "quantity": part["stock_qty"],
            "stock_id": part["stock_id"],
        }
    )



def get_piece_groups(
    search="",
    color_filter="",
    sort_by="color",
    missing_only=False,
    owned_only=False,
    gathering_only=False,
):
    where = ["s.in_gathering = 1"] if gathering_only else ["s.in_collection = ?"]
    params = [] if gathering_only else [int(owned_only)]
    copy_state = "in_gathering" if gathering_only else "in_collection"
    sql = """
        SELECT s.id AS set_id, s.set_num, s.title, s.set_image_url,
               s.theme_name, s.year, s.in_gathering,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num AND other.id <= s.id
                  AND other.{copy_state} = 1) AS copy_number,
               (SELECT COUNT(*) FROM sets other
                WHERE other.set_num = s.set_num
                  AND other.{copy_state} = 1) AS copy_count,
               p.id AS part_id, p.part_num, p.part_name, p.color_id,
               p.color_name, p.quantity, p.missing_quantity, p.image_url, p.item_type
        FROM sets s JOIN set_parts p ON p.set_id = s.id
    """.format(copy_state=copy_state)
    sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.color_name COLLATE NOCASE, p.part_name COLLATE NOCASE, s.set_num"

    # Recherche et filtre couleur comparés sur le nom officiel : « rouge » trouve les pièces « Red ».
    needle = search.casefold()
    color_key = colors.color_group_key(color_filter) if color_filter else ""

    def matches(row):
        if color_key and colors.color_group_key(row["color_name"]) != color_key:
            return False
        if needle:
            haystack = " ".join(
                (
                    str(row["set_num"]),
                    str(row["title"] or ""),
                    str(row["part_num"]),
                    str(row["part_name"] or ""),
                    *colors.search_terms(row["color_name"]),
                )
            ).casefold()
            if needle not in haystack:
                return False
        return True

    with db.database() as connection:
        rows = [row for row in connection.execute(sql, params).fetchall() if matches(row)]
        color_names = [
            row["color_name"]
            for row in connection.execute(
                """
                SELECT DISTINCT p.color_name
                FROM sets s JOIN set_parts p ON p.set_id = s.id
                WHERE (? AND s.in_gathering = 1) OR (NOT ? AND s.in_collection = ?)
                ORDER BY p.color_name COLLATE NOCASE
                """,
                (int(gathering_only), int(gathering_only), int(owned_only)),
            ).fetchall()
        ]

    grouped_parts = {}
    for row in rows:
        key = (row["part_num"], row["color_id"])
        part = grouped_parts.setdefault(
            key,
            {
                "part_num": row["part_num"],
                "part_name": row["part_name"],
                "color_id": row["color_id"],
                "color_name": row["color_name"],
                "color_label": colors.color_group_label(row["color_name"]),
                "color_key": colors.color_group_key(row["color_name"]),
                "image_url": row["image_url"],
                "item_type": row["item_type"] or "part",
                "quantity": 0,
                "missing": 0,
                "sets": [],
            },
        )
        part["quantity"] += row["quantity"]
        part["missing"] += row["missing_quantity"]
        part["sets"].append(
            {
                "id": row["set_id"],
                "title": row["title"],
                "set_num": row["set_num"],
                "theme_name": row["theme_name"],
                "year": row["year"],
                "copy_number": row["copy_number"],
                "copy_count": row["copy_count"],
                "quantity": row["quantity"],
                "missing": row["missing_quantity"],
                "part_id": row["part_id"],
            }
        )

    sort_keys = {
        "color": lambda item: (
            item["color_key"] == "figurine",
            item["color_key"],
            item["part_name"].casefold(),
        ),
        "name": lambda item: (item["part_name"].casefold(), item["color_key"]),
        "missing": lambda item: (-item["missing"], item["color_key"], item["part_name"].casefold()),
        "quantity": lambda item: (-item["quantity"], item["color_key"], item["part_name"].casefold()),
    }
    with db.database() as connection:
        stock_map = {
            (row["part_num"], int(row["color_id"] or 0)): int(row["quantity"])
            for row in connection.execute(
                "SELECT part_num, color_id, quantity FROM stock_parts"
            ).fetchall()
        }
    for key, part in grouped_parts.items():
        part["stock_qty"] = stock_map.get((key[0], int(key[1] or 0)), 0)
    parts = list(grouped_parts.values())
    if missing_only:
        parts = [part for part in parts if part["missing"] > 0]
    parts.sort(key=sort_keys.get(sort_by, sort_keys["color"]))

    # Une couleur peut être enregistrée sous plusieurs graphies : une seule carte.
    color_groups = {}
    for part in parts:
        color_groups.setdefault(part["color_key"], []).append(part)
    if gathering_only:
        for color_parts in color_groups.values():
            for index, part in enumerate(color_parts):
                part["gathering_order"] = index
            color_parts.sort(key=lambda part: part["missing"] == 0)
    groups = [
        {
            "name": color_parts[0]["color_label"],
            "hex": colors.lego_color_hex(color_parts[0]["color_name"]),
            "parts": color_parts,
            "missing": sum(part["missing"] for part in color_parts),
            "quantity": sum(part["quantity"] for part in color_parts),
        }
        for color_parts in color_groups.values()
    ]
    return groups, colors.color_options(color_names), parts



def split_color_groups(groups):
    columns = [[], []]
    heights = [0, 0]
    for group in groups:
        column_index = 0 if heights[0] <= heights[1] else 1
        columns[column_index].append(group)
        heights[column_index] += len(group["parts"]) + 2
    return columns
