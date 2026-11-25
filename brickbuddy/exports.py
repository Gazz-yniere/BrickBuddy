"""Quantités à exporter pour BrickLink et BrickOwl."""
from . import db
from flask import abort, request

def get_export_quantities(owned):
    status_column = "in_collection" if owned else "in_gathering"
    with db.database() as connection:
        parts = connection.execute(
            f"""
            SELECT p.part_num, p.color_id, p.missing_quantity
            FROM sets s JOIN set_parts p ON p.set_id = s.id
            WHERE p.missing_quantity > 0 AND s.{status_column} = 1
                  AND p.item_type = 'part'
            ORDER BY p.part_num, p.color_id
            """
        ).fetchall()
    quantities = {}
    for part in parts:
        key = (part["part_num"], part["color_id"])
        quantities[key] = quantities.get(key, 0) + part["missing_quantity"]
    return quantities



def export_scope():
    scope = request.args.get("scope", "gather")
    if scope not in {"gather", "owned"}:
        abort(400)
    return scope == "owned"
