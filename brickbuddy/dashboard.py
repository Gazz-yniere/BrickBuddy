"""Accueil : un résumé de toute la collection, en une seule lecture."""
from . import db
from . import inventory
from . import prices
from .flask_app import app


def collection_summary():
    """Compteurs de la collection, pour les cartes de l'écran d'accueil."""
    with db.database() as connection:
        counts = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM sets WHERE in_collection = 1) AS owned_sets,
                   (SELECT COUNT(DISTINCT set_num) FROM sets WHERE in_collection = 1) AS owned_numbers,
                   (SELECT COUNT(DISTINCT theme_name) FROM sets
                    WHERE in_collection = 1 AND theme_name != 'Thème non renseigné') AS themes,
                   (SELECT COUNT(*) FROM sets WHERE in_gathering = 1) AS gathering_sets,
                   (SELECT COALESCE(SUM(p.missing_quantity), 0) FROM set_parts p
                    JOIN sets s ON s.id = p.set_id WHERE s.in_gathering = 1) AS to_gather,
                   (SELECT COALESCE(SUM(p.missing_quantity), 0) FROM set_parts p
                    JOIN sets s ON s.id = p.set_id WHERE s.in_collection = 1) AS to_buy,
                   (SELECT COUNT(DISTINCT p.part_num) FROM set_parts p
                    JOIN sets s ON s.id = p.set_id
                    WHERE s.in_collection = 1 AND p.missing_quantity > 0) AS to_buy_refs,
                   (SELECT COUNT(*) FROM set_instructions) AS instructions,
                   (SELECT COUNT(DISTINCT mp.fig_num) FROM minifig_parts mp
                    JOIN sets s ON s.id = mp.set_id WHERE s.in_collection = 1) AS minifigs,
                   (SELECT COALESCE(SUM(quantity), 0) FROM stock_parts) AS stock_pieces,
                   (SELECT COUNT(*) FROM stock_parts) AS stock_refs
            """
        ).fetchone()
        owned = inventory.get_owned_parts(connection)

    priced = [part["line_total"] for part in owned.values() if part["line_total"]]
    return {
        "sets": {
            "copies": counts["owned_sets"],
            "numbers": counts["owned_numbers"],
            "themes": counts["themes"],
        },
        "gathering": {"sets": counts["gathering_sets"], "pieces": counts["to_gather"]},
        "inventory": {
            "references": len(owned),
            "pieces": sum(part["total"] for part in owned.values()),
            "stock_pieces": counts["stock_pieces"],
            "stock_refs": counts["stock_refs"],
        },
        "missing": {"pieces": counts["to_buy"], "references": counts["to_buy_refs"]},
        "building": {"instructions": counts["instructions"], "minifigs": counts["minifigs"]},
        "value": {
            "total": round(sum(priced), 2),
            "priced_parts": len(priced),
        }
        if prices.prices_enabled()
        else None,
    }
