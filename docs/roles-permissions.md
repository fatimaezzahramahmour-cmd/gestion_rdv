# Rôles et permissions

## Modèle de rôles

Le rôle applicatif est stocké dans **`rdv_utilisateur.role`** (modèle `Utilisateur`), lié 1–1 à `auth_user` (Django).

| Valeur | Libellé | Description |
|--------|---------|-------------|
| `admin` | Administrateur | Accès Django Admin, configuration, statistiques |
| `agent` | Agent / réception | Tableau de bord agent, file d'attente, validation RDV |
| `user` | Patient | Extranet, réservation, annulation/modification (règles 24 h) |

En plus, Django fournit des flags sur `User` :

- `is_staff` : accès interface `/admin/` (souvent admin).
- `is_superuser` : tous les droits admin Django.

Un utilisateur avec `is_staff=True` est traité comme **agent** par `_is_agent()` même si `role` n'est pas `agent`.

## Matrice des permissions

Légende : ✅ autorisé · ❌ refusé · ⚠️ conditionnel

### Pages et actions

| Fonctionnalité | URL (name) | Public | Patient (`user`) | Agent | Admin |
|----------------|------------|--------|------------------|-------|-------|
| Accueil vitrine | `/` (`accueil`) | ✅ | ✅ | ✅ | ✅ |
| Connexion | `/login/` | ✅ | ✅ | ✅ | ✅ |
| Inscription | `/signup/` | ❌ (redirige login) | — | — | — |
| Extranet patient | `/extranet/` | ❌ | ✅ | ✅* | ✅* |
| Liste mes RDV | `/mes-rendez-vous/` | ❌ | ✅ (ses RDV) | ✅* | ✅ (tous si admin) |
| Créer RDV | `/rdv/create/` | ❌ | ✅ | ❌** | ❌** |
| Modifier RDV | `/rdv/<pk>/modifier/` | ❌ | ✅*** | ❌ | ❌ |
| Annuler RDV (patient) | `/rdv/<pk>/annuler/` | ❌ | ✅*** | ❌ | ❌ |
| File d'attente (vue patient) | `/file-dattente/` | ❌ | ✅ | ✅ | ✅ |
| Dashboard agent | `/agent/dashboard/` | ❌ | ❌ | ✅ | ⚠️**** |
| File d'attente agent | `/agent/file-dattente/` | ❌ | ❌ | ✅ | ⚠️ |
| Appeler prochain | `/agent/appeler-prochain/` | ❌ | ❌ | ✅ | ⚠️ |
| Valider / annuler RDV (agent) | `/agent/rdv/<pk>/...` | ❌ | ❌ | ✅ | ⚠️ |
| API créneaux | `/rdv/creneaux/` | ❌ | ✅ | ✅ | ✅ |
| Prochain en file | `/rdv/next/` | ❌ | ✅ (sa file) | ✅ | ✅ (global) |
| Dashboard stats custom | `/admin/dashboard/` | ❌ | ❌ | ❌ | ✅ (`staff`) |
| Django Admin | `/admin/` | ❌ | ❌ | ❌ | ✅ (`staff`) |

\* Redirigés vers extranet si ce n'est pas un agent sur les URLs agent.  
\*\* Les agents/admins reçoivent un message d'erreur s'ils tentent de créer un RDV comme un patient.  
\*\*\* Uniquement si `patient_peut_modifier_ou_annuler()` : statut `pending` ou `confirmed`, et **≥ 24 h** avant le RDV.  
\*\*\*\* Un admin avec `is_staff` peut être considéré agent par `_is_agent()`.

### Données visibles

| Donnée | Patient | Agent | Admin |
|--------|---------|-------|-------|
| Ses propres `Rendez_vous` | ✅ | — | ✅ |
| Tous les `Rendez_vous` | ❌ | ✅ (dashboard, file) | ✅ |
| `next_in_queue(user=...)` | Sa file uniquement | File globale (manager) | File globale |
| `Patient` / `Compte` | Son profil (via signaux) | Via admin | Admin complet |
| `JourFermeture`, `Service` | Lecture indirecte (créneaux) | Admin | Admin |

## Règles métier patient (24 h)

Définies dans `rdv/forms.py` :

```python
DELAI_PATIENT_MODIFICATION_HEURES = 24
```

`patient_peut_modifier_ou_annuler(rdv)` retourne `False` si :

- `status` est `done` ou `cancelled`, ou autre que `pending` / `confirmed`.
- Il reste **moins de 24 heures** avant `rdv.date`.

## Statuts d'un rendez-vous

| Statut | Signification | Qui le change |
|--------|---------------|---------------|
| `pending` | En attente (file d'attente) | Défaut à la création |
| `confirmed` | Appelé par l'agent | `agent_appeler_prochain` |
| `done` | Terminé / passé chez le médecin | `rdv_valider` (agent) ou admin |
| `cancelled` | Annulé | Patient (24 h), agent, ou admin |

## Priorités

| Valeur | Libellé | Effet file d'attente |
|--------|---------|----------------------|
| `urgent` | Urgent | Traité en premier |
| `normal` | Cas ordinaire | Après les urgents |
| `control` | Contrôle | Même tri que normal (ordre 1 dans le manager) |

## Création de comptes

| Méthode | Rôle attribué |
|---------|----------------|
| `/signup/` | Désactivé — extranet fermé |
| Migration `0007` | `admin@admin.com` → admin ; `agent@agent.com` → agent |
| Django Admin → Utilisateur | Modifiable manuellement |

## Signaux automatiques (`models.py`)

1. **`post_save` sur `User`** : crée ou met à jour `Utilisateur`.
2. **`post_save` sur `Utilisateur`** : si `role == 'user'`, crée `Patient` + `Compte` (solde 0).

## Recommandations sécurité

- Ne pas laisser les patients s'inscrire avec le rôle `admin` via l'interface publique (déjà le cas : signup force `user`).
- En production : désactiver ou changer les comptes de la migration `0007`.
- Réserver la modification du champ `role` à l'admin Django ou à une commande de management.
