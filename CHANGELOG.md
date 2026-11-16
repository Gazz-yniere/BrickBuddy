# Changelog

Les changements notables apportés à Brick Buddy sont consignés ici.

## 1.0.2

### Modifié

- Dans « Mes sets », les pièces sont regroupées par couleur dans des sections
  repliables, avec une grille de sept pièces par ligne sur grand écran, des
  images de 100 pixels et un compteur « manquantes / total ».
- Les noms et les références longues sont tronqués avec leur texte complet
  accessible au survol. Les en-têtes de couleur de « Mes sets » et de
  l'inventaire reprennent les dégradés de l'application.
- Les commandes de suivi sont alignées à droite dans « Mes sets » ; le bouton
  de suppression du vrac a été retiré au profit des boutons `−` et `+`.
- La démonstration GitHub Pages intègre l'inventaire du set 75193-1 et les
  composants de Chewbacca, avec la grille par couleur et les commandes de
  suivi et de vrac. Les images du set et des pièces sont fournies localement
  depuis Rebrickable ; les états de suivi et le vrac sont fictifs et non persistés.

### Corrigé

- Les modifications des pièces de figurines mettent à jour les compteurs sans
  recharger toute la page ni les images.

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
