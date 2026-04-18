# Gestion RDV – Cabinet dentaire

## Démarrer l’application

1. **Démarrer MySQL (XAMPP)**  
   Ouvrir XAMPP Control Panel → cliquer **Start** à côté de **MySQL**.  
   Sans MySQL démarré, `runserver` affiche : *Can't connect to MySQL server*.

2. **Activer l’environnement virtuel** (PowerShell) :
   ```powershell
   venv\Scripts\activate
   ```

3. **Lancer le serveur** (depuis le dossier `gestion_rdv` à la racine du projet) :
   ```powershell
   py gestion_rdv\manage.py runserver
   ```

4. Ouvrir dans le navigateur : **http://127.0.0.1:8000/**

## Base de données

- MySQL sur `127.0.0.1:3306`
- Base : `gestion_rdv`
- Utilisateur : `root`, mot de passe : (vide)

Créer la base dans phpMyAdmin si elle n’existe pas.
