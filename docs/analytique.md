# Analytique et statistiques

## Vue d'ensemble

L'analytique du projet repose sur la classe utilitaire **`Statistique`** dans `rdv/models.py` (pas un modèle ORM — pas de table dédiée).

Elle agrège les données de la table **`rdv_rendez_vous`** pour alimenter le tableau de bord admin custom.

## Classe `Statistique`

### `calculer_nombre_rendez_vous(filtre=None)`

- **Entrée** : dictionnaire optionnel de filtres Django (`filter(**filtre)`).
- **Sortie** : entier — nombre total de RDV correspondants.
- **Exemple** : `Statistique.calculer_nombre_rendez_vous({'status': 'pending'})`.

### `generer_rapport(debut=None, fin=None)`

- **Entrée** : bornes optionnelles sur `Rendez_vous.date`.
- **Sortie** : dictionnaire Python :

```python
{
    'total': int,           # nombre de RDV dans la période (ou tous)
    'urgent': int,          # RDV avec priority='urgent'
    'by_status': [         # liste de dicts ORM annotate
        {'status': 'pending', 'count': N},
        {'status': 'confirmed', 'count': N},
        ...
    ],
}
```

Implémentation : `values('status').annotate(count=Count('id'))`.

## Tableau de bord admin (`admin_dashboard`)

- **URL** : `/admin/dashboard/`
- **Vue** : `views.admin_dashboard`
- **Accès** : `@staff_member_required` (utilisateur `is_staff=True`)
- **Template** : `rdv/admin_dashboard.html`

### Données affichées

| Variable contexte | Source |
|-------------------|--------|
| `total` | `rapport['total']` |
| `urgent_count` | `rapport['urgent']` |
| `by_status` | `rapport['by_status']` |
| `upcoming` | 10 prochains RDV dans les 7 jours (`date__gte=now`, `date__lte=now+7j`) |

> Le dashboard custom est distinct de la page d'accueil Django Admin (`/admin/`).

## Indicateurs disponibles sans code supplémentaire

Via Django Admin sur `Rendez_vous` :

- Filtres par `date`, `status`, `priority`, `service`, `utilisateur`.
- Actions groupées : confirmer, terminer, annuler, priorité urgent/normal, assigner à moi.

## File d'attente — métriques opérationnelles

Côté **agent dashboard** (`agent_dashboard`) :

| Indicateur | Calcul |
|------------|--------|
| `count_rdv_jour` | RDV du jour (hors `cancelled`) |
| `en_attente_count` | Tous les `pending` |
| `prochain` | `RendezVousManager.next_in_queue_agent_global()` |
| `prochain_pas_aujourdhui` | Alerte si le prochain pending n'est pas à la date du jour |

Côté **patient** (`file_attente_view`) :

- Position dans la file (`queue_position` sur le modèle, ou énumération dans la vue).
- Libellé « Vous » pour le RDV du patient connecté.

## Propriété `queue_position` (modèle)

Calcul 1-based dans `Rendez_vous.queue_position` :

1. Filtre `status='pending'`.
2. Tri : urgent d'abord, puis `date`, puis `created_at`.
3. Index du RDV courant + 1.

Utilisé pour afficher la position du patient dans la file.

## Évolutions analytiques possibles

- Persister des rapports PDF/CSV (export admin).
- Graphiques par service (`Service` × `Rendez_vous`).
- Taux d'annulation, temps moyen d'attente (`created_at` → `done`).
- Exploiter `Compte.solde` pour le chiffre d'affaires patient.
- Table dédiée `StatistiqueJournaliere` si besoin d'historique.

## Requêtes SQL utiles (MySQL)

```sql
-- RDV par statut
SELECT status, COUNT(*) FROM rdv_rendez_vous GROUP BY status;

-- Urgents en attente
SELECT COUNT(*) FROM rdv_rendez_vous
WHERE status = 'pending' AND priority = 'urgent';

-- RDV du jour (adapter le fuseau en application)
SELECT * FROM rdv_rendez_vous
WHERE DATE(date) = CURDATE() AND status != 'cancelled';
```

Les noms de tables Django sont préfixés par l'app : `rdv_rendez_vous`, `rdv_service`, etc.
