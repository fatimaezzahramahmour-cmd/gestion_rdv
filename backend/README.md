# Backend

Django — logique métier, API chatbot, admin.

| Élément | Chemin |
|---------|--------|
| Configuration | `config/settings.py` |
| URLs racine | `config/urls.py` |
| Application | `rdv/` (models, views, chatbot, migrations) |
| Variables d’env | `.env.example` → copier en `.env` |

## Commandes (depuis la racine du dépôt)

```powershell
py backend\manage.py migrate
py backend\manage.py runserver 0.0.0.0:8000
py backend\manage.py test
py backend\manage.py copier_horaires
```
