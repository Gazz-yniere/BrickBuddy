"""Configuration chargée une fois : racine du projet et limites de taille."""
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Un PDF de notice LEGO ne dépasse pas 200 Mo ; une page téléchargée, 5 Mo.
MAX_INSTRUCTION_BYTES = 200 * 1024 * 1024
MAX_INSTRUCTION_PAGE_BYTES = 5 * 1024 * 1024

# Taux livres → euros utilisé tant que le relevé automatique n'a rien rapporté.
DEFAULT_GBP_EUR_RATE = 1.18
