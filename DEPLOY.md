# Guide de déploiement pour game.laviedesza.fr

Ce guide détaille les étapes pour déployer l'application Django sur un serveur Ubuntu avec Gunicorn et Nginx.

## Prérequis

- Un serveur Ubuntu avec accès root ou sudo.
- Le nom de domaine `game.laviedesza.fr` pointant vers l'adresse IP du serveur.

## 1. Préparation du serveur

Mettez à jour le système et installez les paquets nécessaires :

```bash
sudo apt update
sudo apt install python3-venv python3-dev libpq-dev nginx curl
```

## 2. Installation de l'application

Créez le dossier de l'application et clonez/copiez votre code :

```bash
# Création du dossier
sudo mkdir -p /srv/django/treasure_hunt
sudo chown -R $USER:www-data /srv/django/treasure_hunt

# Copiez vos fichiers dans ce dossier.
# Assurez-vous que manage.py est à la racine : /srv/django/treasure_hunt/manage.py
```

Créez l'environnement virtuel et installez les dépendances :

```bash
cd /srv/django/treasure_hunt
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

## 3. Configuration de Django

Appliquez les migrations et collectez les fichiers statiques :

```bash
python manage.py migrate
python manage.py collectstatic
```

## 4. Configuration de Gunicorn

Copiez le fichier de service systemd :

```bash
sudo cp config/gunicorn.service /etc/systemd/system/
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
```

Vérifiez le statut :
```bash
sudo systemctl status gunicorn
```

## 5. Configuration de Nginx

Copiez le fichier de configuration Nginx :

```bash
sudo cp config/nginx.conf /etc/nginx/sites-available/game.laviedesza.fr
sudo ln -s /etc/nginx/sites-available/game.laviedesza.fr /etc/nginx/sites-enabled/
```

Vérifiez la configuration et redémarrez Nginx :

```bash
sudo nginx -t
sudo systemctl restart nginx
```

## 6. Sécurisation avec SSL (Certbot)

Installez Certbot et configurez le SSL :

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d game.laviedesza.fr
```

Suivez les instructions à l'écran. Certbot modifiera automatiquement votre configuration Nginx pour activer HTTPS.

## 7. Finalisation

Une fois le SSL activé, vous pouvez passer les variables de sécurité à `True` dans `config/settings.py` si ce n'est pas déjà fait (voir `SECURE_SSL_REDIRECT`, etc.), puis redémarrer Gunicorn :

```bash
sudo systemctl restart gunicorn
```
