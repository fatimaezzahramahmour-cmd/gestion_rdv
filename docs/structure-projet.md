# Structure du projet

## Arborescence active

```
gestion_rdv/
├── backend/
│   ├── manage.py
│   ├── config/
│   │   ├── settings.py      # Config (Tailscale, MySQL, static, templates)
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── asgi.py
│   └── rdv/
│       ├── models.py
│       ├── views.py
│       ├── urls.py
│       ├── forms.py
│       ├── admin.py
│       ├── chatbot_engine.py
│       ├── chatbot_views.py
│       ├── context_processors.py
│       ├── tests.py
│       ├── migrations/        # 0001 … 0012
│       └── management/commands/
├── frontend/
│   ├── templates/rdv/
│   └── static/rdv/
├── docs/
├── requirements.txt
└── README.md
```

## Supprimé / obsolète

- `gestion_rdv/gestion_rdv/` — ancienne structure imbriquée (doublon)
- `gestion_rdv/rdv/templates/` — déplacé vers `frontend/templates/`
- `gestion_rdv/rdv/static/` — déplacé vers `frontend/static/`
- `signup.html` — inscription publique fermée
- `db.sqlite3`, `__pycache__/` — ignorés par Git

## Rôle des dossiers

| Dossier | Contenu |
|---------|---------|
| `backend/config/` | Projet Django (settings, URLs WSGI) |
| `backend/rdv/` | Code Python uniquement |
| `frontend/templates/` | HTML |
| `frontend/static/` | CSS, JS, images |

Django charge templates et static via `settings.py` :

- `TEMPLATES['DIRS']` → `frontend/templates`
- `STATICFILES_DIRS` → `frontend/static`
