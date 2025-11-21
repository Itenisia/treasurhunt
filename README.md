# Chasse au Trésor

Application Django pour une chasse au trésor avec QR codes.

## Prérequis

- Python 3.10+
- Serveur Web (Nginx)
- Gunicorn
- Un nom de domaine configuré pour pointer vers l'adresse IP du serveur.
- Un utilisateur `sudo` pour le déploiement (ex: `ubuntu`).

## Modèle de Permissions

Le déploiement utilise deux utilisateurs pour une meilleure sécurité :
- **Utilisateur Admin (`ubuntu` par défaut) :** Possède les fichiers du code source, effectue les mises à jour via `git`, et gère les dépendances Python.
- **Utilisateur Web (`www-data`) :** Exécute le serveur d'application (Gunicorn) et n'a les droits d'écriture que sur les répertoires nécessaires (`media/`, `db.sqlite3`).

## Configuration Sudo pour l'Utilisateur Admin

Les scripts de déploiement et de mise à jour utilisent `sudo` pour certaines opérations (ex: redémarrage de Gunicorn, ajustement des permissions). Pour une exécution sans interaction (sans demande de mot de passe), vous devez configurer `sudoers` pour l'utilisateur admin.

**Exemple de configuration `sudoers` (à modifier avec `sudo visudo`) :**

```
# Autoriser l'utilisateur 'ubuntu' à exécuter certaines commandes sans mot de passe
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload-or-restart gunicorn, /usr/bin/chown, /usr/bin/chmod, /usr/bin/mkdir, /usr/bin/apt update, /usr/bin/apt install
```

Adaptez cette ligne en fonction des commandes `sudo` exactes utilisées dans vos scripts et des chemins binaires de votre système. Il est recommandé de n'accorder que les permissions minimales nécessaires.

## Déploiement Initial (Nouveau Serveur)

Le script `deploy.sh` configure l'environnement complet. Il doit être exécuté avec `sudo`.

**ATTENTION :** Avant d'exécuter, assurez-vous que la variable `REPO_URL` dans `scripts/deploy.sh` pointe vers le bon dépôt Git de votre projet.

Si vous utilisez un dépôt PyPI privé, décommentez et configurez la variable `PIP_INDEX_URL` en haut du script `deploy.sh`.

1.  Rendez les scripts exécutables :
    ```bash
    chmod +x scripts/deploy.sh scripts/update.sh
    ```
2.  Exécutez le script de déploiement avec `sudo`. Vous pouvez spécifier un nom d'utilisateur admin différent en deuxième argument.
    ```bash
    # Syntaxe : sudo ./scripts/deploy.sh <domaine> [utilisateur_admin]
    sudo ./scripts/deploy.sh your_domain.com ubuntu
    ```

## Mise à jour du site (Après Déploiement Initial)

Pour mettre à jour l'application, connectez-vous en tant qu'**utilisateur admin (`ubuntu`)** et exécutez le script `update.sh`. Ce script n'a pas besoin de `sudo` pour être lancé, il l'utilisera en interne pour les commandes qui le nécessitent.

Si vous utilisez un dépôt PyPI privé, assurez-vous que la variable `PIP_INDEX_URL` est également configurée dans `scripts/update.sh`.

Ce script `update.sh` a été renforcé pour la production et inclut :
-   Une gestion rigoureuse des erreurs (`set -euo pipefail`).
-   Un verrou de déploiement pour éviter les exécutions concurrentes.
-   Un système de logs détaillé dans `logs/` avec horodatage.
-   Un workflow Git sécurisé (`git fetch --prune`, `git reset --hard`) avec vérification des modifications locales.
-   L'activation et la désactivation automatiques d'une page de maintenance (`config/maintenance.html`) pendant la mise à jour.
-   Une sauvegarde automatique de la base de données (`db.sqlite3`) avant les migrations.
-   Un redémarrage gracieux de Gunicorn avec vérification de son état et affichage des logs en cas d'échec.

```bash
# Exécuter en tant qu'utilisateur admin (ex: ubuntu)
cd /srv/django/treasure_hunt/
./scripts/update.sh
```

Ce script effectue les actions suivantes :
1.  Active le mode maintenance.
2.  Récupère le dernier code depuis Git (`git pull` équivalent sécurisé).
3.  Met à jour les dépendances Python (`pip install --upgrade`).
4.  Sauvegarde la base de données.
5.  Applique les migrations de base de données (`migrate`).
6.  Collecte les fichiers statiques (`collectstatic`).
7.  Ajuste les permissions sur les fichiers média et la base de données.
8.  Désactive le mode maintenance.
9.  Redémarre le service Gunicorn en utilisant `sudo`.
