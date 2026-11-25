"""Sauvegarde de la base avant une mise à jour : `python -m brickbuddy.backup`."""
from . import db
from pathlib import Path
import contextlib
import sqlite3
import sys

# La copie vit à côté de la base, dans le volume monté par Docker : elle survit au
# remplacement du conteneur.
BACKUP_NAME = "bdd.bak"


def backup_target(destination=None):
    """Destination de la copie : `bdd.bak` à côté de la base, ou celle demandée."""
    return Path(destination) if destination else db.DATABASE_PATH.parent / BACKUP_NAME


def backup_database(destination=None):
    """
    Copie la base dans `bdd.bak`.

    L'API de sauvegarde de SQLite est utilisée, pas une copie de fichier : le mode WAL
    est absorbé et la copie est complète même si l'application écrit pendant la relève.
    """
    source_path = db.DATABASE_PATH
    if not source_path.exists():
        raise FileNotFoundError(f"Aucune base à sauvegarder : {source_path}")
    target = backup_target(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    # `with connection` ne ferme pas la connexion (Windows garde le fichier ouvert) :
    # « closing » la ferme vraiment.
    with contextlib.closing(sqlite3.connect(source_path)) as source:
        with contextlib.closing(sqlite3.connect(target)) as copy:
            source.backup(copy)
            # La copie doit être un fichier seul : le mode journal classique reporte le
            # WAL dans le fichier et supprime les fichiers annexes « bdd.bak-wal ».
            copy.execute("PRAGMA journal_mode = DELETE")
    return target


def main(argv=None):
    """Point d'entrée du service `backup` de Docker Compose et de la ligne de commande."""
    argv = argv if argv is not None else sys.argv[1:]
    target = backup_database(argv[0] if argv else None)
    print(f"Base sauvegardée : {target}")
    return target


if __name__ == "__main__":
    main()
