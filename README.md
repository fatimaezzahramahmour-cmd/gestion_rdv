# Gestion RDV – Cabinet dentaire

Application Django : rendez-vous, file d'attente, chatbot, espaces patient / agent / admin.

## Structure du projet (à utiliser)

```
gestion_rdv/                 # Racine Git
├── backend/                 # Django
│   ├── manage.py
│   ├── config/              # settings, urls, wsgi
│   └── rdv/                   # App métier
├── frontend/                # Templates + static
│   ├── templates/rdv/
│   └── static/rdv/
├── docs/                      # Documentation
├── venv/
└── requirements.txt
```

> **Ne plus utiliser** l’ancien dossier `gestion_rdv/gestion_rdv/` (supprimé).

## Démarrage

```powershell
venv\Scripts\activate
# XAMPP : MySQL démarré, base gestion_rdv
py backend\manage.py migrate
py backend\manage.py runserver 0.0.0.0:8000
```

**Tailscale :** `http://<ton-ip-tailscale>:8000/` (ex. `http://100.103.204.35:8000/`)

## Comptes

| Rôle | Email | Mot de passe |
|------|-------|--------------|
| Admin | admin@admin.com | admin123 |
| Agent | agent@agent.com | agent123 |

Les **patients** n’ont pas d’inscription publique : comptes créés par l’admin Django (`/admin/`).

## URLs utiles

| Page | URL |
|------|-----|
| Accueil | `/` |
| Connexion | `/login/` |
| Django Admin | `/admin/` |
| Dashboard admin métier | `/admin/dashboard/` |

Documentation détaillée : [docs/README.md](docs/README.md)
