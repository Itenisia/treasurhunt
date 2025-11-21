#!/bin/bash

# ==============================================================================
# Script de mise à jour robuste pour Chasse au Trésor
#
# Améliorations :
# - Gestion des erreurs (set -euo pipefail)
# - Verrou de déploiement pour éviter les exécutions concurrentes
# - Logging de la sortie dans un fichier
# - Workflow Git sécurisé (fetch/reset, vérification des modifs locales)
# - Vérification du Virtualenv
# - Sauvegarde de la base de données avant migration
# - Redémarrage gracieux de Gunicorn avec vérification
# - Mode maintenance (à configurer côté Nginx)
# ==============================================================================

# --- Gestion des erreurs et de la configuration ---
set -euo pipefail

# --- Variables de configuration ---
PROJECT_DIR="/srv/django/treasure_hunt"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/update_$(date +%Y%m%d_%H%M%S).log"
LOCK_FILE="$PROJECT_DIR/.deploy.lock"
MAINTENANCE_FILE="$PROJECT_DIR/maintenance_on.flag"

GIT_BRANCH="master" # Branche à déployer
ADMIN_USER="ubuntu"
WEB_USER="www-data"
WEB_GROUP="www-data"

# Création du dossier de logs et ajustement des droits si nécessaire, avant la redirection
mkdir -p "$LOG_DIR"
chown "$ADMIN_USER":"$WEB_GROUP" "$LOG_DIR"

# Redirection de toute la sortie (stdout et stderr) vers le fichier de log
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "--- Début de la mise à jour : $(date) ---"

# --- Verrou de déploiement ---
if [ -f "$LOCK_FILE" ]; then
    echo "ERREUR: Un déploiement est déjà en cours (lock file trouvé)."
    exit 1
fi
touch "$LOCK_FILE"
# Assurer la suppression du verrou et du fichier de maintenance à la fin du script
trap 'rm -f "$LOCK_FILE" "$MAINTENANCE_FILE"' EXIT

# --- Vérifications préliminaires ---
if [ "$(id -u)" -ne "$(id -u "$ADMIN_USER")" ]; then
    echo "ERREUR: Ce script doit être exécuté par l'utilisateur '$ADMIN_USER'."
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "ERREUR: L'environnement virtuel n'a pas été trouvé à '$VENV_DIR'."
    exit 1
fi

# --- Mode Maintenance (Activation) ---
echo "--- Activation du mode maintenance ---"
touch "$MAINTENANCE_FILE"

cd "$PROJECT_DIR" || exit

# --- Workflow Git ---
echo "--- Vérification du statut Git ---"
if ! git diff-index --quiet HEAD --; then
    echo "ERREUR: Des modifications locales non commitées ont été détectées. Veuillez les commit ou les stash."
    exit 1
fi

echo "--- Récupération des dernières sources (branche: $GIT_BRANCH) ---"
git fetch --prune origin
git reset --hard origin/"$GIT_BRANCH"

# --- Mise à jour des dépendances ---
echo "--- Mise à jour des dépendances Python ---"
"$VENV_DIR"/bin/pip install --upgrade -r requirements.txt
# Pour plus de sécurité, envisagez d'utiliser --require-hashes

# --- Sauvegarde de la base de données ---
echo "--- Sauvegarde de la base de données ---"
DB_FILE="$PROJECT_DIR/db.sqlite3"
if [ -f "$DB_FILE" ]; then
    cp "$DB_FILE" "$PROJECT_DIR/backup_db_$(date +%Y%m%d_%H%M%S).sqlite3"
fi

# --- Migrations et statiques ---
echo "--- Application des migrations et collecte des statiques ---"
"$VENV_DIR"/bin/python manage.py migrate
"$VENV_DIR"/bin/python manage.py collectstatic --noinput

# --- Permissions ---
echo "--- Ajustement des permissions ---"
# Créer le dossier media s'il n'existe pas
mkdir -p "$PROJECT_DIR/media/"
sudo chown -R "$WEB_USER":"$WEB_GROUP" "$PROJECT_DIR/media/"
# Assurer que les fichiers statiques sont lisibles par le serveur web
if [ -d "$PROJECT_DIR/staticfiles" ]; then
    sudo chown -R "$WEB_USER":"$WEB_GROUP" "$PROJECT_DIR/staticfiles/"
    sudo chmod -R 755 "$PROJECT_DIR/staticfiles/"
fi
if [ -f "$DB_FILE" ]; then
    sudo chown "$WEB_USER":"$WEB_GROUP" "$DB_FILE"
    sudo chmod 664 "$DB_FILE"
fi

# --- Désactivation du mode maintenance (si tout s'est bien passé jusqu'ici) ---
echo "--- Désactivation du mode maintenance ---"
rm -f "$MAINTENANCE_FILE"

# --- Redémarrage du service ---
echo "--- Redémarrage de Gunicorn ---"
sudo systemctl reload-or-restart gunicorn

# Vérification du statut du service après redémarrage
sleep 5 # Laisser un peu de temps au service pour démarrer
if ! sudo systemctl is-active --quiet gunicorn; then
    echo "ERREUR: Le service Gunicorn n'a pas pu redémarrer correctement."
    echo "--- Dernières lignes du journal Gunicorn ---"
    journalctl -u gunicorn --no-pager -n 20
    # Ici, on pourrait ajouter une logique de rollback
    exit 1
fi

echo "--- Mise à jour terminée avec succès : $(date) ---"

exit 0
