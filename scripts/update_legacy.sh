#!/bin/bash

# Script de mise à jour pour Chasse au Trésor
# À exécuter en tant que l'utilisateur admin (ex: 'ubuntu')

set -e

# --- Variables de configuration ---
PROJECT_DIR="/srv/django/treasure_hunt"
VENV_DIR="$PROJECT_DIR/venv"
WEB_USER="www-data"
WEB_GROUP="www-data"

# Décommentez et configurez si vous utilisez un dépôt PyPI privé
# PIP_INDEX_URL="http://votre.pypi.repo/simple"
PIP_EXTRA_ARGS=""

echo "--- Début de la mise à jour ---"

# 1. Aller dans le répertoire du projet
cd $PROJECT_DIR || exit

# 2. Récupérer le dernier code
echo "--- Pull du code source ---"
git pull origin master

# 3. Mise à jour des dépendances Python
echo "--- Mise à jour des dépendances Python ---"
# Configuration pour un dépôt PyPI privé
if [ -n "$PIP_INDEX_URL" ]; then
    PIP_EXTRA_ARGS="--index-url $PIP_INDEX_URL"
    if [[ $PIP_INDEX_URL == http://* ]]; then
        DOMAIN_PYPI=$(echo $PIP_INDEX_URL | awk -F/ '{print $3}')
        PIP_EXTRA_ARGS="$PIP_EXTRA_ARGS --trusted-host $DOMAIN_PYPI"
    fi
fi

$VENV_DIR/bin/pip install $PIP_EXTRA_ARGS -r requirements.txt

# 4. Migrations et fichiers statiques
echo "--- Application des migrations et collecte des statiques ---"
$VENV_DIR/bin/python manage.py migrate
$VENV_DIR/bin/python manage.py collectstatic --noinput

# 5. Permissions
# Les fichiers appartiennent à l'utilisateur admin et au groupe web.
# Seuls les fichiers/dossiers nécessitant une écriture par le serveur web sont ajustés.
echo "--- Ajustement des permissions pour les fichiers média et la base de données ---"
sudo chown -R $WEB_USER:$WEB_GROUP $PROJECT_DIR/media/
sudo chown $WEB_USER:$WEB_GROUP $PROJECT_DIR/db.sqlite3
sudo chmod 664 $PROJECT_DIR/db.sqlite3

# 6. Redémarrage du service Gunicorn
echo "--- Redémarrage de Gunicorn (nécessite sudo) ---"
sudo systemctl restart gunicorn

echo "--- Mise à jour terminée avec succès ! ---"
