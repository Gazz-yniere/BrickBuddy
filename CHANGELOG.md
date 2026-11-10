# Changelog

Les changements notables apportés à Brick Buddy sont consignés ici.

## Première version publique

### Fonctionnalités

- Suivi séparé des sets possédés et des sets dont les pièces sont à réunir.
- Gestion de plusieurs exemplaires, avec état des pièces indépendant pour chaque copie.
- Inventaire des pièces trouvées, quantités manquantes et regroupement par couleur.
- Recherche, filtres, images en cache et métadonnées Rebrickable optionnelles.
- Export des listes au format XML BrickLink et CSV BrickOwl.
- Connexion par mot de passe partagé, protection CSRF et limitation des tentatives.
- Stockage SQLite persistant, utilisable en local ou avec Docker Compose.

### Publication et qualité

- Présentation et documentation de démarrage réorganisées.
- Tests automatisés sur GitHub Actions.
- Workflow de publication multi-architecture vers Docker Hub sur les tags de version.
- Validation Docker sans publication sur les pull requests et publication sur les releases.
- Logo Brick Buddy dans le README et captures détaillées des pièces réelles du set 75457-1.
- Exclusion des secrets, bases locales et caches du dépôt Git.
