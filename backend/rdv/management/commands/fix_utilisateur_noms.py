"""Remplit les noms vides des profils Utilisateur."""
from django.core.management.base import BaseCommand

from rdv.models import Utilisateur


class Command(BaseCommand):
    help = "Complète le champ nom des utilisateurs vides."

    def handle(self, *args, **options):
        fixed = 0
        for profil in Utilisateur.objects.select_related("user"):
            if (profil.nom or "").strip():
                continue
            nom = (profil.user.get_full_name() or "").strip()
            if not nom and profil.user.email:
                nom = profil.user.email.split("@")[0].replace(".", " ").title()
            if not nom:
                nom = profil.user.username
            profil.nom = nom
            profil.save(update_fields=["nom"])
            fixed += 1
            self.stdout.write(f"  {profil.user.username} -> {nom}")
        self.stdout.write(self.style.SUCCESS(f"{fixed} profil(s) mis à jour."))
