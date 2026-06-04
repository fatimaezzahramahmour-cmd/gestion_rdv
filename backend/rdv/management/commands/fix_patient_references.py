"""Corrige les références UUID patient dupliquées en base."""
import uuid

from django.core.management.base import BaseCommand

from rdv.models import Patient


class Command(BaseCommand):
    help = "Attribue un UUID unique à chaque patient (corrige les doublons)."

    def handle(self, *args, **options):
        seen = set()
        fixed = 0
        for patient in Patient.objects.all().order_by("id"):
            ref = patient.reference
            if ref in seen:
                patient.reference = uuid.uuid4()
                patient.save(update_fields=["reference"])
                fixed += 1
                self.stdout.write(f"  Corrigé: {patient.nom or patient.user.username}")
            else:
                seen.add(ref)
        self.stdout.write(self.style.SUCCESS(f"Terminé — {fixed} référence(s) corrigée(s)."))
