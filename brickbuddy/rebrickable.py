"""Client Rebrickable : inventaire, thème, figurines d'un set."""
from . import brickowl
from . import db
from . import settings
import json
import time
import urllib.error
import urllib.parse
import urllib.request

def rebrickable_get(path):
    api_key = settings.setting_value("REBRICKABLE_API_KEY")
    if not api_key:
        raise RuntimeError("Ajoutez la clé Rebrickable sur la page Paramètres, ou REBRICKABLE_API_KEY dans le fichier .env, pour importer automatiquement les pièces.")

    separator = "&" if "?" in path else "?"
    url = f"https://rebrickable.com/api/v3/lego/{path}{separator}{urllib.parse.urlencode({'key': api_key})}"
    req = urllib.request.Request(url, headers={"User-Agent": "LegoList/1.0"})
    with db.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = time.time()
        next_request_at = connection.execute(
            "SELECT next_request_at FROM rebrickable_request_gate WHERE id = 1"
        ).fetchone()["next_request_at"]
        request_at = max(now, next_request_at)
        connection.execute(
            "UPDATE rebrickable_request_gate SET next_request_at = ? WHERE id = 1",
            (request_at + 1.1,),
        )
    time.sleep(max(0, request_at - now))
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 404:
            raise ValueError("Référence de set introuvable sur Rebrickable.") from error
        if error.code in (401, 403):
            raise ValueError("La clé Rebrickable est invalide ou n'a pas accès à l'API.") from error
        if error.code == 429:
            raise RuntimeError(
                "Rebrickable a limité les requêtes. L'opération est arrêtée sans nouvelle tentative ; réessaie plus tard."
            ) from error
        raise RuntimeError(f"Rebrickable a répondu avec l'erreur {error.code}.") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("Impossible de joindre Rebrickable. Vérifiez votre connexion puis réessayez.") from error



def fetch_set_info(set_num):
    return rebrickable_get(f"sets/{urllib.parse.quote(set_num, safe='-')}/")



def fetch_theme_name(theme_id):
    theme = rebrickable_get(f"themes/{int(theme_id)}/")
    return theme.get("name") or f"Thème {theme_id}"



def fetch_set_inventory(set_num):
    set_info = fetch_set_info(set_num)
    parts = {}
    next_page = f"sets/{urllib.parse.quote(set_num, safe='-')}/parts/?page_size=1000"
    while next_page:
        page = rebrickable_get(next_page)
        for item in page.get("results", []):
            if item.get("is_spare"):
                continue
            color = item.get("color") or {}
            part = item.get("part") or {}
            key = (part.get("part_num", ""), int(color.get("id") or 0))
            if not key[0]:
                continue
            brickowl_part = brickowl.brickowl_external_id(part.get("external_ids"), "BrickOwl")
            brickowl_color = brickowl.brickowl_external_id(color.get("external_ids"), "BrickOwl")
            entry = parts.setdefault(
                key,
                {
                    "part_num": key[0],
                    "part_name": part.get("name") or key[0],
                    "color_id": key[1],
                    "color_name": color.get("name") or "Unknown",
                    "quantity": 0,
                    "image_url": part.get("part_img_url") or "",
                    "item_type": "part",
                    # Reference BrickOwl « BOID-couleur » : la source directe du prix.
                    "brickowl_boid": (
                        f"{brickowl_part}-{brickowl_color}"
                        if brickowl_part and brickowl_color
                        else ""
                    ),
                },
            )
            entry["quantity"] += int(item.get("quantity") or 0)
        next_page = page.get("next")
        if next_page:
            parsed = urllib.parse.urlparse(next_page)
            next_page = parsed.path.removeprefix("/api/v3/lego/")
            if parsed.query:
                next_page += f"?{parsed.query}"

    minifigs = {}
    try:
        figs_next = (
            f"sets/{urllib.parse.quote(set_num, safe='-')}/minifigs/?page_size=1000"
        )
        while figs_next:
            page = rebrickable_get(figs_next)
            for item in page.get("results", []):
                fig_num = item.get("set_num") or ""
                if not fig_num.startswith("fig-"):
                    continue
                try:
                    fig_quantity = int(item.get("quantity") or 0)
                except (TypeError, ValueError):
                    continue
                if fig_quantity <= 0:
                    continue
                minifigs[(fig_num, 0)] = {
                    "part_num": fig_num,
                    "part_name": item.get("set_name") or fig_num,
                    "color_id": 0,
                    "color_name": "Figurine",
                    "quantity": fig_quantity,
                    "image_url": item.get("set_img_url") or "",
                    "item_type": "minifig",
                }
            figs_next = page.get("next")
            if figs_next:
                parsed = urllib.parse.urlparse(figs_next)
                figs_next = parsed.path.removeprefix("/api/v3/lego/")
                if parsed.query:
                    figs_next += f"?{parsed.query}"
    except (RuntimeError, ValueError):
        pass

    for key, minifig in minifigs.items():
        parts.setdefault(key, minifig)
    return set_info, list(parts.values())



def fetch_minifig_parts_for_set(set_num):
    """Récupère la composition de chaque figurine d'un set (informatif uniquement)."""
    rows = []
    figs_next = f"sets/{urllib.parse.quote(set_num, safe='-')}/minifigs/?page_size=1000"
    seen_fig_nums = set()
    while figs_next:
        page = rebrickable_get(figs_next)
        for item in page.get("results", []):
            fig_num = item.get("set_num") or ""
            if not fig_num.startswith("fig-"):
                continue
            try:
                fig_quantity = int(item.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
            if fig_quantity <= 0 or fig_num in seen_fig_nums:
                continue
            seen_fig_nums.add(fig_num)
            try:
                parts_next = (
                    f"minifigs/{urllib.parse.quote(fig_num, safe='-')}"
                    "/parts/?page_size=1000"
                )
                fig_rows = {}
                while parts_next:
                    parts_page = rebrickable_get(parts_next)
                    for part_item in parts_page.get("results", []):
                        color = part_item.get("color") or {}
                        part = part_item.get("part") or {}
                        part_num = part.get("part_num") or ""
                        if not part_num:
                            continue
                        try:
                            color_id = int(color.get("id") or 0)
                        except (TypeError, ValueError):
                            color_id = 0
                        try:
                            quantity = int(part_item.get("quantity") or 0)
                        except (TypeError, ValueError):
                            quantity = 0
                        key = (part_num, color_id)
                        entry = fig_rows.get(key)
                        if entry is None:
                            fig_rows[key] = {
                                "fig_num": fig_num,
                                "part_num": part_num,
                                "part_name": part.get("name") or part_num,
                                "color_id": color_id,
                                "color_name": color.get("name") or "Unknown",
                                "quantity": quantity,
                                "image_url": part.get("part_img_url") or "",
                            }
                        else:
                            entry["quantity"] += quantity
                    parts_next = parts_page.get("next")
                    if parts_next:
                        parsed = urllib.parse.urlparse(parts_next)
                        parts_next = parsed.path.removeprefix("/api/v3/lego/")
                        if parsed.query:
                            parts_next += f"?{parsed.query}"
            except (RuntimeError, ValueError):
                continue
            rows.extend(
                row for row in fig_rows.values() if row["quantity"] > 0
            )
        figs_next = page.get("next")
        if figs_next:
            parsed = urllib.parse.urlparse(figs_next)
            figs_next = parsed.path.removeprefix("/api/v3/lego/")
            if parsed.query:
                figs_next += f"?{parsed.query}"
    return rows



def _rebrickable_next_page(next_url):
    """URL de la page suivante d'Rebrickable, en chemin relatif pour le client."""
    if not next_url:
        return ""
    parsed = urllib.parse.urlparse(next_url)
    path = parsed.path.removeprefix("/api/v3/lego/")
    return f"{path}?{parsed.query}" if parsed.query else path
