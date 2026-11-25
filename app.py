"""Brick Buddy : application Flask pour organiser une collection LEGO.

Le code est découpé dans le paquet brickbuddy/ (un module par sujet, des
routes par famille de pages). Ce fichier reste le point d'entrée public :
``python app.py``, ``gunicorn app:app`` et les tests l'importent tel quel.
"""
import os
import threading
import urllib.request

from brickbuddy import assets, auth, brickowl, colors, db, exports, images, instructions, inventory, prices, rebrickable
from brickbuddy.config import BASE_DIR, MAX_INSTRUCTION_BYTES, MAX_INSTRUCTION_PAGE_BYTES
from brickbuddy.db import DATABASE_PATH
from brickbuddy.flask_app import app
from brickbuddy.routes import auth as auth_routes
from brickbuddy.routes import build as build_routes
from brickbuddy.routes import exports as export_routes
from brickbuddy.routes import media as media_routes
from brickbuddy.routes import pages as pages_routes
from brickbuddy.routes import parts as parts_routes
from brickbuddy.routes import prices as prices_routes
from brickbuddy.routes import sets as sets_routes
from brickbuddy.routes import sets_refresh as sets_refresh_routes

# Surface publique conservée : les tests et les scripts appellent ces noms via
# app.py. Pour bouchonner une fonction, patcher le module qui la définit
# (brickbuddy.db, brickbuddy.prices, …), pas cette façade.
asset_version = assets.asset_version
template_assets = assets.template_assets
authentication_config_error = auth.authentication_config_error
authentication_version = auth.authentication_version
safe_redirect_target = auth.safe_redirect_target
brickowl_color_ids = brickowl.brickowl_color_ids
brickowl_external_id = brickowl.brickowl_external_id
brickowl_get = brickowl.brickowl_get
BRICKOWL_COLOR_CACHE = brickowl.BRICKOWL_COLOR_CACHE
extract_brickowl_price = brickowl.extract_brickowl_price
fetch_set_boids = brickowl.fetch_set_boids
lookup_brickowl_boid = brickowl.lookup_brickowl_boid
official_color_name = colors.official_color_name
lego_color_hex = colors.lego_color_hex
database = db.database
initialize_database = db.initialize_database
navigation_stats = db.navigation_stats
export_scope = exports.export_scope
get_export_quantities = exports.get_export_quantities
IMAGE_CACHE_PATH = images.IMAGE_CACHE_PATH
local_image_url = images.local_image_url
instruction_cover_url = images.instruction_cover_url
LegoInstructionParser = instructions.LegoInstructionParser
find_lego_instructions = instructions.find_lego_instructions
instruction_order = instructions.instruction_order
instruction_set = instructions.instruction_set
lego_instruction_url = instructions.lego_instruction_url
save_instruction = instructions.save_instruction
get_gathering_minifig_parts_map = inventory.get_gathering_minifig_parts_map
get_minifig_parts_map = inventory.get_minifig_parts_map
get_owned_parts = inventory.get_owned_parts
get_piece_groups = inventory.get_piece_groups
replace_set_minifig_parts = inventory.replace_set_minifig_parts
DEFAULT_GBP_EUR_RATE = prices.DEFAULT_GBP_EUR_RATE
claim_price_refresh = prices.claim_price_refresh
gbp_to_eur = prices.gbp_to_eur
load_price_map = prices.load_price_map
price_eur = prices.price_eur
price_refresh_running = prices.price_refresh_running
price_targets = prices.price_targets
prices_enabled = prices.prices_enabled
record_part_price = prices.record_part_price
refresh_part_prices = prices.refresh_part_prices
request_price_refresh = prices.request_price_refresh
fetch_minifig_parts_for_set = rebrickable.fetch_minifig_parts_for_set
fetch_set_inventory = rebrickable.fetch_set_inventory
fetch_set_info = rebrickable.fetch_set_info
fetch_theme_name = rebrickable.fetch_theme_name
rebrickable_get = rebrickable.rebrickable_get

initialize_database()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
