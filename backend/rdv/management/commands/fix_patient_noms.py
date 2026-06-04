"""Corrige les champs nom patient quand ils contiennent un e-mail."""
from django.core.management.base import BaseCommand

from rdv.models import Patient


class Command(BaseCommand):
    help = "Remplace les noms patients qui sont des e-mails par un libellé lisible."

    def handle(self, *args, **options):
        fixed = 0
        for patient in Patient.objects.select_related("user"):
            nom = (patient.nom or "").strip()
            email = (patient.user.email or "").strip().lower()
            if nom and email and nom.lower() != email and "@" not in nom:
                continue
            full = (patient.user.get_full_name() or "").strip()
            if full:
                new_nom = full
            elif patient.user.username and "@" not in patient.user.username:
                new_nom = patient.user.username
            elif email:
                new_nom = email.split("@")[0].replace(".", " ").title()
            else:
                new_nom = "Patient"
            if new_nom != nom:
                patient.nom = new_nom
                patient.save(update_fields=["nom"])
                fixed += 1
                self.stdout.write(f"  {new_nom}")
        self.stdout.write(self.style.SUCCESS(f"{fixed} nom(s) corrigé(s)."))
