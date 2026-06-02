"""
Commande: copie les horaires cabinet du Lundi et Mardi vers Mercredi, Jeudi et Vendredi.
À lancer une fois après avoir saisi Lundi/Mardi dans Django Admin.

Usage (depuis le dossier où se trouve manage.py):
  python manage.py copier_horaires
"""
from django.core.management.base import BaseCommand
from rdv.models import HoraireCabinet


class Command(BaseCommand):
    help = "Copie les horaires du Lundi et Mardi vers Mercredi, Jeudi et Vendredi (mêmes plages)."

    def handle(self, *args, **options):
        # Lundi=0, Mardi=1 → on copie vers Mercredi=2, Jeudi=3, Vendredi=4
        source_jours = [0, 1]  # Lundi, Mardi
        target_jours = [2, 3, 4]  # Mercredi, Jeudi, Vendredi

        created = 0
        for h in HoraireCabinet.objects.filter(jour__in=source_jours, actif=True):
            for j in target_jours:
                if HoraireCabinet.objects.filter(
                    jour=j,
                    heure_ouverture=h.heure_ouverture,
                    heure_fermeture=h.heure_fermeture,
                ).exists():
                    continue
                HoraireCabinet.objects.create(
                    jour=j,
                    heure_ouverture=h.heure_ouverture,
                    heure_fermeture=h.heure_fermeture,
                    actif=True,
                )
                created += 1
                self.stdout.write(
                    f"  Créé: {h.get_jour_display()} → {dict(HoraireCabinet.JOURS)[j]} "
                    f"{h.heure_ouverture} - {h.heure_fermeture}"
                )

        if created == 0:
            self.stdout.write(
                self.style.WARNING(
                    "Aucun nouvel horaire créé. Soit Mercredi/Jeudi/Vendredi ont déjà les mêmes plages, "
                    "soit ajoute d’abord Lundi et Mardi dans Admin → Horaires cabinet."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"Terminé. {created} horaire(s) créé(s)."))
