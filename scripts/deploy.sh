#!/bin/bash

# Script de déploiement pour Chasse au Trésor
# À exécuter avec sudo ou en tant que root

set -e # Arrête le script en cas d'erreur

# --- Variables de configuration ---
# Le nom de domaine doit être passé en argument
if [ -z "$1" ]; then
    echo "Usage: $0 VOTRE_NOM_DE_DOMAINE [UTILISATEUR_ADMIN]"
    echo "Exemple: $0 your_domain.com ubuntu"
    exit 1
fi

DOMAIN_NAME="$1"
ADMIN_USER="${2:-ubuntu}" # 'ubuntu' par défaut, peut être surchargé par le 2ème argument

PROJECT_DIR="/srv/django/treasure_hunt"
REPO_URL="https://github.com/your_github_username/treasure_hunt.git" # À CHANGER
WEB_USER="www-data"
WEB_GROUP="www-data"

# Décommentez et configurez si vous utilisez un dépôt PyPI privé
# PIP_INDEX_URL="http://votre.pypi.repo/simple"
PIP_EXTRA_ARGS=""

# --- Début du script ---

echo "--- Début du déploiement pour $DOMAIN_NAME ---"
echo "--- Utilisateur admin: $ADMIN_USER, Utilisateur web: $WEB_USER ---"

# 1. Installation des dépendances système
'''
echo "--- Installation des paquets système ---"
apt update
apt install -y python3-venv python3-dev nginx curl git
'''
# 2. Configuration des utilisateurs et permissions
echo "--- Configuration des utilisateurs et permissions ---"
# Crée le répertoire projet et définit les propriétaires
mkdir -p $PROJECT_DIR
usermod -aG $WEB_GROUP $ADMIN_USER
chown -R $ADMIN_USER:$WEB_GROUP $PROJECT_DIR
chmod 775 $PROJECT_DIR
chmod g+s $PROJECT_DIR # Assure que les nouveaux fichiers héritent du groupe

# 3. Clonage ou copie du code source par l'utilisateur admin
echo "--- Récupération du code source ---"
# En production, utilisez git. L'option `sudo -u` est cruciale.
# sudo -u $ADMIN_USER git clone $REPO_URL $PROJECT_DIR
# Pour ce test, on copie et on ajuste les droits
cp -r ./* $PROJECT_DIR/
chown -R $ADMIN_USER:$WEB_GROUP $PROJECT_DIR

# 4. Création de l'environnement virtuel et installation des dépendances
echo "--- Installation des dépendances Python (en tant que $ADMIN_USER) ---"
sudo -u $ADMIN_USER python3 -m venv $PROJECT_DIR/venv

# Configuration pour un dépôt PyPI privé
if [ -n "$PIP_INDEX_URL" ]; then
    PIP_EXTRA_ARGS="--index-url $PIP_INDEX_URL"
    if [[ $PIP_INDEX_URL == http://* ]]; then
        DOMAIN_PYPI=$(echo $PIP_INDEX_URL | awk -F/ '{print $3}')
        PIP_EXTRA_ARGS="$PIP_EXTRA_ARGS --trusted-host $DOMAIN_PYPI"
    fi
fi

sudo -u $ADMIN_USER $PROJECT_DIR/venv/bin/pip install $PIP_EXTRA_ARGS -r $PROJECT_DIR/requirements.txt
sudo -u $ADMIN_USER $PROJECT_DIR/venv/bin/pip install $PIP_EXTRA_ARGS gunicorn

# 5. Configuration de Django
echo "--- Configuration de Django (en tant que $ADMIN_USER) ---"
sudo -u $ADMIN_USER $PROJECT_DIR/venv/bin/python $PROJECT_DIR/manage.py migrate
sudo -u $ADMIN_USER $PROJECT_DIR/venv/bin/python $PROJECT_DIR/manage.py collectstatic --noinput

# 6. Configuration de Nginx et Certbot
echo "--- Configuration de Nginx pour la validation Certbot ---"
mkdir -p /var/www/html/.well-known/acme-challenge
chown -R $WEB_USER:$WEB_GROUP /var/www/html
sed "s/YOUR_DOMAIN_NAME/$DOMAIN_NAME/g" $PROJECT_DIR/config/nginx.pre-ssl.conf > /etc/nginx/sites-available/$DOMAIN_NAME
ln -sf /etc/nginx/sites-available/$DOMAIN_NAME /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

echo "--- Installation de Certbot et génération du certificat ---"
apt install -y certbot python3-certbot-nginx
certbot --nginx -d $DOMAIN_NAME --non-interactive --agree-tos -m admin@$DOMAIN_NAME

# 7. Configuration finale de Nginx avec SSL
echo "--- Configuration finale de Nginx avec SSL ---"
sed "s/YOUR_DOMAIN_NAME/$DOMAIN_NAME/g" $PROJECT_DIR/config/nginx.post-ssl.conf > /etc/nginx/sites-available/$DOMAIN_NAME
nginx -t && systemctl restart nginx

# 8. Configuration et démarrage de Gunicorn
echo "--- Configuration du service Gunicorn ---"
# S'assurer que le service Gunicorn est configuré pour tourner avec $WEB_USER
cp $PROJECT_DIR/config/gunicorn.service /etc/systemd/system/
systemctl start gunicorn
systemctl enable gunicorn

# 9. Finalisation des permissions
echo "--- Finalisation des permissions ---"
# L'utilisateur admin possède les fichiers, le groupe web peut y accéder
chown -R $ADMIN_USER:$WEB_GROUP $PROJECT_DIR
# Le serveur web (www-data) doit pouvoir écrire dans les dossiers media et la DB
chown -R $WEB_USER:$WEB_GROUP $PROJECT_DIR/media/
# Le fichier de DB doit être accessible en écriture par www-data
touch $PROJECT_DIR/db.sqlite3 # S'assure que le fichier existe avant de changer les droits
chown $WEB_USER:$WEB_GROUP $PROJECT_DIR/db.sqlite3
chmod 664 $PROJECT_DIR/db.sqlite3

echo "--- Déploiement terminé avec succès pour $DOMAIN_NAME ---"
echo "--- Le site est maintenant accessible à https://$DOMAIN_NAME ---"

exit 0
