# Documentation — Gestion RDV (cabinet dentaire)

Application web Django pour la prise de rendez-vous, la file d'attente et la gestion d'un cabinet dentaire.

## Sommaire

| Document | Contenu |
|----------|---------|
| [Architecture](architecture.md) | Stack technique, couches, flux HTTP, diagrammes |
| [Rôles et permissions](roles-permissions.md) | Admin, agent, patient — qui peut faire quoi |
| [Analytique et statistiques](analytique.md) | Rapports, KPIs, tableau de bord admin |
| [Base de données](base-de-donnees.md) | Tables MySQL, champs, relations, migrations |
| [Structure du projet](structure-projet.md) | Chaque dossier et fichier, rôle et contenu |

## Démarrage rapide

Voir le [README principal](../README.md) à la racine du dépôt :

1. Démarrer **MySQL** (XAMPP).
2. Activer le venv : `venv\Scripts\activate`
3. Lancer : `py backend\manage.py runserver`
4. Ouvrir : http://127.0.0.1:8000/

## Comptes de démonstration (migration `0007`)

| Rôle | Email | Mot de passe | Redirection après login |
|------|-------|--------------|-------------------------|
| Admin | `admin@admin.com` | `admin123` | `/admin/` (Django Admin) |
| Agent | `agent@agent.com` | `agent123` | `/agent/dashboard/` |
| Patient | Compte créé par admin | — | `/extranet/` |

> En production, changez immédiatement ces mots de passe et ne les exposez pas publiquement.

## Stack en bref

- **Backend** : Django 6.x, Python 3
- **Base** : MySQL (`gestion_rdv`) via `pymysql`
- **Fuseau** : `Africa/Casablanca`
- **Frontend** : templates Django + CSS (`theme.css`, `style.css`) + JS (`app.js`)
