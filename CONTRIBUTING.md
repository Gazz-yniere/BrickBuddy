# Contribuer à Brick Buddy

Merci de contribuer ! Une proposition de fonctionnalité ou un signalement de
bogue est bienvenu via les [issues](https://github.com/Gazz-yniere/BrickBuddy/issues).
Pour un changement important, ouvre d'abord une issue afin de discuter de son périmètre.

## Préparer l'environnement

Les tests automatisés du projet utilisent Python 3.12. Depuis le dossier du projet :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pytest
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Renseigne la clé générée et un mot de passe personnel dans `.env` comme expliqué
dans le [README](README.md#configuration-commune), puis lance `python app.py`.
Une clé Rebrickable est facultative.

## Proposer un changement

1. Crée une branche dédiée et limite tes modifications au sujet traité.
2. Ajoute ou adapte les tests et la documentation concernés.
3. Lance `python -m pytest -q`. Pour le JavaScript, si Node.js est installé,
   vérifie la syntaxe avec `node --check static/app.js` et, pour le site,
   `node --check docs/demo.js`.
4. Vérifie le comportement sur petit écran pour tout changement visuel.
5. Ouvre une pull request décrivant le problème, la solution et les vérifications
   effectuées. Ajoute des captures pour les changements d'interface.

Le site GitHub Pages se trouve dans [`docs/`](docs/). Sa démonstration utilise
uniquement des données fictives en mémoire ; ne la relie pas à des données
personnelles ou à une instance réelle de l'application.

## Données et sécurité

Ne publie jamais de mot de passe, clé API, fichier `.env`, base de données,
cache d'images personnel ou sauvegarde. Vérifie `git status` et le contenu du
diff avant toute contribution. Si tu découvres une vulnérabilité, évite de
divulguer des informations sensibles dans une issue publique et contacte le
mainteneur en privé.

En proposant une contribution, tu acceptes qu'elle soit distribuée sous la
[licence MIT](LICENSE).
