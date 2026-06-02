# Frontend

Templates et fichiers statiques servis par Django (`backend/config/settings.py`).

| Dossier | Contenu |
|---------|---------|
| `templates/rdv/` | Pages HTML (accueil, login, extranet, agent, admin…) |
| `static/rdv/css/` | `theme.css`, `style.css`, `extranet.css` |
| `static/rdv/js/` | `app.js`, `chatbot-widget.js` |
| `static/rdv/images/` | Logo, photos, `dentist-avatar.png` (chatbot) |

Le widget chatbot est chargé dans `base_public.html`, `base.html` et `accueil.html`.
