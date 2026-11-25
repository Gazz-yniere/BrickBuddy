# Changelog

Les changements notables apportés à Brick Buddy sont consignés ici.

## 1.0.3

### Ajouté

- HTML, CSS et JavaScript sont servis comprimés (gzip) : le premier affichage
  d'une page demande beaucoup moins d'octets.
- Pages jamais gardées en cache (`no-store`) et fichiers statiques versionnés
  gardés un an (`immutable`) : plus de mélange entre une vieille page et un CSS
  devenu étranger, et plus de rechargement du CSS à chaque navigation.
- Polices Google chargées sans bloquer l'affichage, y compris sur la page de
  connexion ; la page se structure avec le CSS critique pendant qu'elles
  arrivent.
- SQLite passe en mode WAL avec un délai d'attente des verrous, et gagne deux
  index (`sets.set_num`, `set_instructions.set_num`) : les pages restent
  rapides même pendant un téléchargement de notice.
- **Les pages de l'atelier se mettent à jour sans rechargement** : un filtre, une
  couleur, un compteur, un ajout de vrac ou un bouton d'actualisation remplacent
  la zone de résultats, les compteurs de la barre latérale suivent et les panneaux
  déjà ouverts le restent. Les chips d'origine et le lien « Effacer » travaillent
  de la même façon. La déconnexion et l'écran de connexion gardent une navigation
  normale.
- Dans « Mes sets », chaque carte affiche une pastille visible sans la déplier :
  `▤ 3 notices` quand des notices sont enregistrées pour la référence,
  `▤ Pas de notice` quand il n'y en a aucune. Les notices étant partagées entre
  les exemplaires d'un même set, la pastille est la même sur tous.
- **Les prix des pièces s'affichent dans l'inventaire**, quand l'option est
  activée sur la page « Paramètres » ou dans le fichier `.env` : chaque carte porte
  « prix · 0,14 € l'unité · 1,68 € » pour la pièce et pour sa quantité, et une tuile
  **« valeur estimée »** réunit le total de l'inventaire à côté des autres compteurs.
  Une ligne précise d'où viennent les prix et depuis quand.
- Les prix viennent de **BrickOwl** (l'API Rebrickable n'en fournit aucun) et
  sont **relevés une fois par jour**, en arrière-plan, au premier affichage de
  l'inventaire : la page reste immédiate, les prix affichés sont ceux de la
  dernière relève, et une coupure réseau ne casse rien. Les prix BrickOwl étant
  en livres, ils sont convertis en euros avec le taux relevé chaque jour.
- Un bouton **« Rafraîchir les prix »** est placé dans le bloc Prix de la page
  « Paramètres » : il relance la relève de toutes les références connues sur-le-champ,
  sans attendre le lendemain, et la page confirme ce qui s'est passé (« toutes tes
  pièces sont relevées une à une, en arrière-plan », ou bien « une relève est déjà en
  cours »). Les prix mis à jour apparaissent dès la page suivante. Pendant une relève,
  la tuile **« valeur estimée »** de l'inventaire annonce « relève en cours » et se met
  à jour quand tu reviens sur la page ; la page n'est jamais redemandée toute seule.
- **Les relevés de prix sont journalisés** : le journal affiche l'heure de départ,
  chaque appel envoyé à BrickOwl (référence concernée, jamais la clé API), la
  progression tous les 25 appels, puis le bilan (« 45 prix relevés, 10 références
  sans prix »). On voit enfin quand l'application interroge BrickOwl et ce
  qu'elle rapporte.
- **« Accueil » est la page d'entrée de l'application** : six cartes en deux colonnes,
  dans le style du thème, résument toute la collection — sets possédés, pièces à
  réunir, inventaire, pièces à acheter, notices disponibles et valeur estimée — et
  chaque carte mène directement à son écran.
- **Une page « Paramètres »** en bas du menu : elle enregistre la clé Rebrickable,
  la clé BrickOwl et la case « Afficher les prix » dans la base, sans toucher au
  fichier `.env`. Une clé enregistrée est remplacée par le message « Clé enregistrée
  dans l'application » et ne paraît jamais à l'écran ni dans le journal. Une pastille
  courte indique d'où vient la clé utilisée aujourd'hui : « Enregistrée dans l'app »,
  « Clé du fichier .env » ou « Aucune clé ».
- **Le taux livres → euros se relève tout seul**, une fois par jour, chez un
  service public de change, en arrière-plan : les prix sont convertis avec le taux
  du jour sans que tu aies à l'écrire. Le bouton « Mettre à jour maintenant » de la
  page « Paramètres » force un relevé et annonce le taux obtenu (« Taux mis à jour :
  1,240 € pour 1 £ ») ; si le service est injoignable, le taux connu reste utilisé et
  le message le dit.
- **Une sauvegarde de la base avant toute mise à jour** : `docker compose run --rm backup`
  (ou `python -m brickbuddy.backup` hors Docker) copie la base dans `data/bdd.bak`, à côté
  du fichier utilisé par l'application. La copie est faite par SQLite : elle est complète
  même si l'application écrit au même moment, et elle tient dans un seul fichier. Pour
  revenir en arrière, remplace `data/legolist.db` par cette copie puis redémarre.

### Modifié

- Dans « Mes sets », « Suivre » s'appelle maintenant **« Rechercher »** ; le lien
  Rebrickable devient la **seule icône `↗`** et le bouton d'actualisation la
  **flèche circulaire `↻`**, chacun gardant son libellé au survol.
- La page « Construire » tient dans **un seul panneau « Notices du set »** : le
  bloc « Recherche des notices LEGO » a disparu. Le compte rendu (« 2 notices
  enregistrées · 3 à télécharger ») et, s'il y a lieu, le bouton d'action
  tiennent sur la ligne du titre.
- Les notices trouvées chez LEGO et pas encore enregistrées **entrent dans le
  carrousel**, à la suite des notices enregistrées, avec leur bordure pointillée
  et un bouton « Télécharger » ; la tuile se clique aussi pour lancer le
  téléchargement.
- Les notices enregistrées sont affichées en tuiles, au format des résultats de
  recherche : badge « Livre n » en haut, couverture LEGO, intitulé, nom du
  fichier, puis **« Ouvrir » au-dessus de « Retirer »** : les boutons sont empilés,
  de même largeur, et ne sortent jamais de la carte.
- Les notices enregistrées forment un carrousel : les flèches `←` et `→` sont
  placées hors des tuiles, une avant la première et une après la dernière ;
  elles changent la notice lue, en faisant le tour de la liste, et ne
  **parcourent que les notices enregistrées**. La tuile elle-même se clique
  (image, titre, fond de la carte) pour choisir le livre ; « Ouvrir » et
  « Retirer » gardent leur rôle. Sans JavaScript, ce sont de simples liens ;
  avec un seul fichier, aucune flèche n'apparaît. Le livre lu est **toujours
  entier dans le carrousel**, placé une largeur et demie après le bord gauche :
  les livres d'avant restent visibles, et le premier est collé à gauche.
- Le lecteur de notice est un bloc de la page, **à la même largeur que les
  autres panneaux** : il ne déborde plus de la zone de contenu et ne crée aucun
  défilement horizontal. Son bandeau comme son fond reprennent la couleur
  sombre du thème. **Tant qu'aucune notice n'est enregistrée, il reste masqué** :
  la page ne montre qu'un cadre vide.
- Le bandeau « Chargement de la notice… » s'efface dès que le navigateur a
  affiché le PDF : il ne reste plus bloqué avec sa petite roue.
- Les notices enregistrées s'affichent **instantanément** : chaque fichier est
  servi sous une adresse immuable que le navigateur conserve, et les livres
  voisins sont préchargés pendant que la page est au repos (sauf fichier de
  plus de 25 Mo, jamais téléchargé en arrière-plan). Changer de notice ne
  demande plus d'attente.
- Une couverture LEGO qui ne se charge pas est remplacée par le visuel vide,
  sans icône d'image cassée.
- L'astuce « Si la notice ne s'affiche pas, utilise Ouvrir » est placée
  au-dessus du lecteur.
- La recherche LEGO se lance automatiquement à l'ouverture de la page, même
  quand des notices sont déjà enregistrées : le bouton « Rechercher les notices
  LEGO » et son texte d'introduction ont été supprimés. Le panneau garde un
  bouton « Rechercher les notices » tant qu'il n'y a rien à télécharger, et
  « Réessayer » après un échec.
- **Télécharger une notice ne recharge plus la page** : la proposition se
  transforme en carte de notice enregistrée, le lecteur affiche le PDF
  immédiatement, et le compte rendu se met à jour. Le bouton « Tout
  télécharger » enchaîne les téléchargements un par un, sans rechargement.
- Le bouton « Tout télécharger » n'apparaît qu'à partir de 2 notices à
  enregistrer ; avec une seule notice, seul le bouton de sa tuile reste proposé.
  Il apparaît et disparaît tout seul quand la liste change, sans rechargement.
- **Le numéro de chaque livre ne change plus jamais** : la tuile téléchargée, la
  carte enregistrée et la liste LEGO portent le même « Livre n », dans l'ordre où
  LEGO les présente. Les PDF ajoutés à la main sont numérotés à part,
  « Ajout 1 », « Ajout 2 », et n'empruntent pas les numéros des livres LEGO.
- L'ajout manuel d'une notice est une **zone de dépôt** : on clique dedans pour
  choisir un PDF, on peut aussi le glisser dessus ; le nom et la taille du
  fichier s'affichent, et le bouton « Ajouter » ne s'active qu'avec un PDF.
  L'ajout se fait sans recharger la page : les livres trouvés chez LEGO restent
  affichés et le lecteur bascule sur le fichier ajouté.
- La fenêtre de confirmation est **sobre et commune à toute l'application** :
  l'icône d'avertissement est alignée sur les boutons, et le titre, le message
  et le libellé du bouton s'adaptent à ce qui est demandé (« Retirer la notice »,
  « Retirer le set », « Supprimer ces pièces »).
- Le bouton **« Exporter la liste »** n'apparaît plus que dans **« Pièces
  manquantes »** : c'est là qu'on prépare une commande. Le panneau d'export de
  « Pièces à réunir » a été retiré.
- **Le CSS est refait de fond en comble** : les couleurs et les réglages généraux
  vivent dans un seul fichier de variables, puis quinze feuilles rangées par rôle
  (critique, socle, layout, composants, écran de connexion, accueil, pièces, sets,
  inventaire, pièces manquantes, vérification, notices, paramètres, responsive).
  Plus aucun CSS dans les fichiers de page : tout est dans les feuilles. Le
  JavaScript est découpé en quatre petits fichiers chargés l'un après l'autre, et le
  code de l'application est réparti en modules d'environ cinq cents lignes chacun :
  un fichier ne dépasse plus mille lignes.
- Les chips d'origine de l'inventaire (« Tout », « En vrac », …) reprennent les
  couleurs du thème : même bordure, même fond, même texte que les autres blocs.
- **Les noms de couleur restent en anglais, partout** : « Red » ne devient plus
  « Rouge » sur les cartes, les menus « Couleur » ni les pastilles. Le nom officiel
  de Rebrickable est le seul affiché ; une saisie en français (« rouge ») est
  toujours reconnue par le filtre et la recherche, mais jamais affichée.
- **Le menu de côté est épuré** : la note et le bloc profil du bas ont été retirés,
  « Déconnexion » descend tout en bas du menu et « Paramètres » vient juste au-dessus.
- **La barre du haut ne porte plus que le nom de l'écran** (« PIÈCES À RÉUNIR »,
  …), en orange avec son étoile `✦` ; « MON ATELIER » et la ligne d'introduction
  au-dessus du titre ont été supprimés sur chaque page.
- Les fichiers de tests sont regroupés dans le dossier `tests/`, avec un fichier de
  préparation commun.
- **Les flèches des panneaux repliables** (sets, couleurs, figurines) sont une simple
  flèche centrée, sans rond ; elles se colorent au survol et basculent quand le
  panneau est ouvert.
- **Le bouton « Déconnexion » occupe toute la largeur du menu de côté**, plus haut et
  centré ; il reste lisible sur petit écran.
- **Le panneau « Ajouter du vrac » de l'inventaire** est un vrai panneau déroulant,
  pleine largeur, avec des champs dont le fond se voit : il reste ouvert après un
  ajout, le message de succès paraît en haut de la page et les compteurs se mettent à
  jour sans recharger la page.

### Corrigé

- Les prix ne restaient plus coincés : une référence que BrickOwl ne connaît pas
  est maintenant marquée « sans prix » pour un mois au lieu d'être ignorée. Elle
  ne revient plus en tête de file, et les autres références de l'inventaire
  obtiennent leur prix au lieu d'attendre derrière elle. La relève n'a plus de
  plafond : elle traite toutes les références connues.
- Les pages ne restent plus bloquées en texte brut, sans feuille de style, avec
  des images géantes. Une adresse de CSS ou de JavaScript introuvable est
  désormais servie sans cache : le navigateur ne la répète plus pendant un an
  et recharge la feuille de style dès la page suivante.
- Le `?v=` des fichiers statiques est calculé sur leur contenu : il change tout
  seul quand le CSS ou le JavaScript change, la page de connexion et les pages
  de l'atelier utilisent la même version, et un numéro oublié ne peut plus
  pointer sur un fichier disparu.
- Le squelette de la page (barre latérale, en-tête, zone de contenu, images
  cadrées) est dans la feuille critique, chargée en premier : une page est
  structurée dès le premier tracé, même si les autres feuilles arrivent en retard.
- La page des notices ne provoque plus d'erreur à l'affichage à cause d'un
  argument `selected_index` jamais défini.
- **Retirer une notice ne recharge plus la page** : la carte disparaît, le livre
  retrouve sa place dans la liste des livres trouvés chez LEGO, avec son numéro,
  et les autres résultats restent affichés. Le lecteur passe sur la notice
  suivante, ou se masque s'il ne reste rien à lire.
- Le bouton « Télécharger » ne déborde plus de sa tuile, ni sur petit écran, ni
  quand le nom du fichier est long.
- L'ascenseur du carrousel des notices ne touche plus les tuiles : un espace est
  ménagé entre les cartes et la barre de défilement, y compris sur petit écran.
- Le bilan du bouton « Tout télécharger » ne provoquait plus aucune action : sa
  phrase était mal écrite, le message « 3 notices enregistrées » s'affiche de
  nouveau.
- Le compte rendu n'affiche plus « 0 notice enregistrée » quand il n'y en a
  aucune : il ne garde que le nombre de livres à télécharger.
- **Une couleur ne se disperse plus en plusieurs cartes** : une couleur venue de
  Rebrickable (« Red ») et la même couleur saisie à la main (« rouge ») forment une
  seule carte, sur tous les écrans. Le menu « Couleur » ne propose plus deux lignes
  pour la même couleur, les cartes portent le nom officiel anglais de la couleur, et
  le filtre comme la recherche acceptent n'importe quelle graphie : taper « rouge »
  trouve les pièces enregistrées sous « Red ». Les nuances proches restent distinctes
  (« Blue » et « Dark Blue » restent deux cartes).
- **Les pastilles de couleur suivent enfin leur couleur** : une nuance peu courante
  (« Dark Bluish Gray », « Tan »…) affichait une pastille grise. Elles prennent
  maintenant la teinte officielle de la couleur, comme l'entête de la carte ; une
  figurine garde sa pastille dorée et une pièce « sans couleur » reste grise.
- **Un set que plus aucun écran ne montre est vraiment retiré** : « Retirer cet
  exemplaire vendu » dans « Mes sets », le `×` d'un set que tu ne possèdes plus dans
  « Pièces à réunir », et « Retirer de Mes sets » suppriment le set et ses pièces au
  lieu de laisser une ligne invisible en mémoire. Les pièces d'un set retiré ne
  comptent plus dans l'inventaire, et la notice reste disponible pour les autres
  exemplaires de la même référence. Les sets déjà stockés sans écran (reliquats
  d'anciennes ventes) sont nettoyés à la suppression. Le `×` d'un set ni possédé ni
  en recherche demande une confirmation, comme les autres actions qui détruisent
  des données.
- **La popin de confirmation fonctionne de nouveau** : « Retirer le set » et
  « Annuler » ne se fermaient plus et affichaient « La page n'a pas pu être mise à
  jour ». La confirmation ferme la popin, l'action est envoyée comme les autres,
  la carte disparaît sur-le-champ sans rechargement de la page.
- **Plus aucune couleur parasite au chargement** : la page ne se colorait pas d'un
  orange puis d'un vert avant l'arrivée des feuilles de style. Le chargement des
  feuilles est direct, et le squelette comme les couleurs sont garantis dès le
  premier tracé.
- **Les images des figurines ne débordent plus** de leur carte, ni dans « Pièces à
  réunir » ni dans le panneau des composants d'une figurine.
- **« Prendre dans le vrac » ne comptait plus deux fois** : la pièce était retirée du
  vrac une fois, puis une seconde fois par le renvoi du formulaire ; la quantité
  baissait deux fois.
- **Ajouter du vrac ne rechargait plus la page** et refermait le panneau ; un champ de
  couleur restait vide et le nom de la pièce se perdait. Le panneau reste ouvert, le
  message de succès paraît et les compteurs suivent.

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
