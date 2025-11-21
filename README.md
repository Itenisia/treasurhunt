# Chasse au Trésor

Application Django pour une chasse au trésor avec QR codes.

## Prérequis

- Python 3.10+
- Serveur Web (Nginx)
- Gunicorn

## Installation

Voir le fichier [DEPLOY.md](DEPLOY.md) pour les instructions détaillées de déploiement sur le serveur.

## Structure des dossiers sur le serveur

Le projet est déployé dans `/srv/django/treasure_hunt`.
L'utilisateur système exécutant le site est `www-data`.

## Mise à jour du site

Un script de mise à jour est disponible pour automatiser le déploiement des nouvelles versions.

```bash
sudo /srv/django/treasure_hunt/scripts/update.sh
```

Ce script effectue les actions suivantes :
1.  Récupère le dernier code depuis Git (`git pull`).
2.  Met à jour les dépendances Python (`pip install`).
3.  Applique les migrations de base de données (`migrate`).
4.  Collecte les fichiers statiques (`collectstatic`).
5.  Redémarre le service Gunicorn.
