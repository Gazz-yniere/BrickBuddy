# Changelog

Les changements notables apportés à Brick Buddy sont consignés ici.

## 1.0.1

### Ajouté

- Suivi des composants de figurines, avec quantités distinctes pour chaque set
  et prise en compte de plusieurs exemplaires d'une même figurine.
- Vérification d'un set à partir du vrac, aperçu des quantités et transfert
  des pièces disponibles.
- Site GitHub Pages de présentation et de documentation, avec démo interactive
  autonome : navigation entre les vues, recherche et suivi d'un set et d'une
  figurine fictifs, sans sauvegarde ni serveur.
- Guide de contribution et licence MIT.

### Modifié

- Synchronisation entre l'état d'une figurine et les quantités de ses
  composants ; les états sont conservés à l'actualisation de l'inventaire.
- Images et commandes des pièces de figurines agrandies et harmonisées avec les
  autres pièces, noms tronqués et couleurs affichées sur les images.
- Boutons des sets alignés dans « Mes sets » et prise depuis le vrac accessible
  par pièce dans « Pièces à réunir ».
- Suppression de l'ajout manuel sur les cartes « Sets à réunir » ; il reste
  disponible dans « Mes sets ».

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
