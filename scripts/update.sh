#!/bin/bash

# Script de mise à jour pour Chasse au Trésor
# À exécuter en tant que root ou avec sudo

PROJECT_DIR="/srv/django/treasure_hunt"
VENV_DIR="$PROJECT_DIR/venv"
USER="www-data"
GROUP="www-data"

echo "Début de la mise à jour..."

# 1. Aller dans le répertoire du projet
cd $PROJECT_DIR || exit

# 2. Récupérer le dernier code
echo "Pull du code..."
# On s'assure que les permissions sont correctes pour git pull si on est root
# mais que le repo appartient à un autre user, ou on force le pull en tant que root
git pull origin master

# 3. Mise à jour des dépendances
echo "Mise à jour des dépendances..."
$VENV_DIR/bin/pip install -r requirements.txt

# 4. Migrations
echo "Application des migrations..."
$VENV_DIR/bin/python manage.py migrate

# 5. Fichiers statiques
echo "Collecte des fichiers statiques..."
$VENV_DIR/bin/python manage.py collectstatic --noinput

# 6. Permissions (au cas où)
echo "Correction des permissions..."
chown -R $USER:$GROUP $PROJECT_DIR

# 7. Redémarrage du service
echo "Redémarrage de Gunicorn..."
systemctl restart gunicorn

echo "Mise à jour terminée avec succès !"
