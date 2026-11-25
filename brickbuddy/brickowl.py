"""Client BrickOwl : prix et références « BOID-couleur »."""
from . import db
from . import prices
from . import rebrickable
from . import settings
from .flask_app import app
import json
import time
import urllib.error
import urllib.parse
import urllib.request

# Rebrickable publie les numéros BrickOwl de chaque couleur : la table est rechargée
# une fois par jour, en mémoire, pour les pièces saisies à la main.
BRICKOWL_COLOR_CACHE = {"fetched_at": 0.0, "ids": {}}



# Champs de « catalog/price_history » dans l'ordre de préférence : la moyenne
# des offres actives, puis la moins chère si aucune vente récente n'existe.
BRICKOWL_PRICE_KEYS = (
    "current_average_all",
    "current_average_new",
    "current_average_used",
    "current_min_all",
)



def brickowl_external_id(external_ids, key):
    """Identifiant BrickOwl d'une piece ou d'une couleur, tel que Rebrickable le publie."""
    entry = (external_ids or {}).get(key)
    if isinstance(entry, list):
        values = entry
    elif isinstance(entry, dict):
        values = entry.get("ext_ids") or []
    else:
        values = []
    for value in values:
        text = str(value if value is not None else "").strip()
        if text and text.lower() not in {"none", "null"}:
            return text
    return ""



def brickowl_request_summary(query):
    """Résumé lisible d'une requête BrickOwl, sans la clé API."""
    return " ".join(f"{key}={value}" for key, value in sorted(query.items()) if key != "key")



def brickowl_get(path, params=None):
    """Requête vers l'API BrickOwl, cadencée comme celle de Rebrickable."""
    api_key = settings.setting_value("BRICKOWL_API_KEY")
    if not api_key:
        raise RuntimeError("Ajoutez la clé BrickOwl sur la page Paramètres, ou BRICKOWL_API_KEY dans le fichier .env, pour afficher les prix.")

    query = dict(params or {})
    query["key"] = api_key
    url = f"https://api.brickowl.com/v1/{path}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": "BrickBuddy/1.0"})
    with db.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = time.time()
        next_request_at = connection.execute(
            "SELECT next_request_at FROM brickowl_request_gate WHERE id = 1"
        ).fetchone()["next_request_at"]
        request_at = max(now, next_request_at)
        connection.execute(
            "UPDATE brickowl_request_gate SET next_request_at = ? WHERE id = 1",
            (request_at + 0.12,),
        )
    time.sleep(max(0, request_at - now))
    app.logger.info("BrickOwl : %s %s", path, brickowl_request_summary(query))
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ValueError("La clé BrickOwl est invalide ou n'a pas accès à l'API.") from error
        if error.code in (400, 404):
            raise LookupError("Référence introuvable sur BrickOwl.") from error
        if error.code == 429:
            raise RuntimeError(
                "BrickOwl a limité les requêtes ; les prix restent ceux de la dernière mise à jour."
            ) from error
        raise RuntimeError(f"BrickOwl a répondu avec l'erreur {error.code}.") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("Impossible de joindre BrickOwl. Vérifiez votre connexion.") from error
    if isinstance(payload, dict) and (payload.get("error") or payload.get("status") == "error"):
        raise LookupError("Référence introuvable sur BrickOwl.")
    return payload



def brickowl_payload_data(payload):
    """BrickOwl enveloppe ses réponses dans « data » ; on la retire ici."""
    if isinstance(payload, dict):
        return payload.get("data", payload)
    return payload



def lookup_brickowl_boid(part_num, color_id):
    """
    Référence BrickOwl « BOID-couleur » d'une pièce saisie à la main, via Rebrickable.

    Une pièce seule n'est jamais paginée : le portique impose une attente par
    requête, donc la relève ne demande cette référence que si elle est vraiment
    nouvelle, et laisse l'erreur remonter plutôt que de la transformer en
    « référence sans prix ».
    """
    part_info = rebrickable.rebrickable_get(f"parts/{urllib.parse.quote(part_num, safe='-')}/")
    brickowl_part = brickowl_external_id(part_info.get("external_ids"), "BrickOwl")
    brickowl_color = brickowl_color_ids().get(int(color_id or 0))
    if not brickowl_part or not brickowl_color:
        return ""
    return f"{brickowl_part}-{brickowl_color}"



def fetch_set_boids(set_num):
    """
    Toutes les références BrickOwl d'un set, en lisant son inventaire paginé.

    Une requête par page de 1000 pièces au lieu d'une requête par référence : un
    gros set coûte quelques appels Rebrickable, pas un millier. Les figurines
    n'ont pas de référence BrickOwl et sont ignorées.

    Retourne les références trouvées et le nombre de pièces lues : un inventaire
    qui ne répond pas n'est pas un inventaire « sans référence ».
    """
    path = f"sets/{urllib.parse.quote(set_num, safe='-')}/parts/?page_size=1000"
    boids = {}
    pages = 0
    rows = 0
    while path and pages < prices.PRICE_BOID_SET_LIMIT:
        page = rebrickable.rebrickable_get(path)
        pages += 1
        for item in page.get("results", []):
            part_num = str(item.get("part_num") or "").strip()
            if not part_num:
                continue
            rows += 1
            try:
                color_id = int(item.get("color_id") or 0)
            except (TypeError, ValueError):
                continue
            if color_id == prices.MINIFIG_COLOR_ID:
                continue
            brickowl_part = brickowl_external_id(item.get("external_ids"), "BrickOwl")
            brickowl_color = brickowl_color_ids().get(color_id)
            if brickowl_part and brickowl_color:
                boids[(part_num, color_id)] = f"{brickowl_part}-{brickowl_color}"
        path = rebrickable._rebrickable_next_page(page.get("next"))
    return boids, rows



def brickowl_color_ids():
    """Table « couleur Rebrickable → numéro BrickOwl », rechargée une fois par jour."""
    cache = BRICKOWL_COLOR_CACHE
    if cache["ids"] and time.time() - cache["fetched_at"] < prices.PRICE_REFRESH_SECONDS:
        return cache["ids"]
    mapping = {}
    next_page = "colors/?page_size=1000"
    while next_page:
        page = rebrickable.rebrickable_get(next_page)
        for row in page.get("results", []):
            brickowl_color = brickowl_external_id(row.get("external_ids"), "BrickOwl")
            try:
                color_id, brickowl_color_id = int(row.get("id")), int(brickowl_color)
            except (TypeError, ValueError):
                continue
            if color_id > 0 and brickowl_color_id > 0:
                mapping[color_id] = brickowl_color_id
        next_page = page.get("next")
        if next_page:
            parsed = urllib.parse.urlparse(next_page)
            next_page = parsed.path.removeprefix("/api/v3/lego/")
            if parsed.query:
                next_page += f"?{parsed.query}"
    if mapping:
        cache["ids"] = mapping
        cache["fetched_at"] = time.time()
    return cache["ids"]



def extract_brickowl_price(payload):
    """Prix courant d'un article en livres, dans la réponse de « catalog/price_history »."""
    data = brickowl_payload_data(payload)
    if not isinstance(data, dict):
        return None
    for key in BRICKOWL_PRICE_KEYS:
        try:
            number = float(data.get(key))
        except (TypeError, ValueError):
            continue
        if number > 0:
            return round(number, 3)
    return None
