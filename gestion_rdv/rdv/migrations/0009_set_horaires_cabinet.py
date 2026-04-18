# Data migration: horaires cabinet
# Lundi–Jeudi: 8h00–12h55 et 14h00–18h05 | Vendredi: 8h00–12h55

from datetime import time
from django.db import migrations


def set_horaires(apps, schema_editor):
    HoraireCabinet = apps.get_model('rdv', 'HoraireCabinet')
    HoraireCabinet.objects.all().delete()

    # Lundi (0), Mardi (1), Mercredi (2), Jeudi (3): matin 8:00-12:55, après-midi 14:00-18:05
    for jour in [0, 1, 2, 3]:
        HoraireCabinet.objects.create(jour=jour, heure_ouverture=time(8, 0), heure_fermeture=time(12, 55), actif=True)
        HoraireCabinet.objects.create(jour=jour, heure_ouverture=time(14, 0), heure_fermeture=time(18, 5), actif=True)
    # Vendredi (4 / jm3a): 8:00-12:55 seulement
    HoraireCabinet.objects.create(jour=4, heure_ouverture=time(8, 0), heure_fermeture=time(12, 55), actif=True)


def reverse_horaires(apps, schema_editor):
    HoraireCabinet = apps.get_model('rdv', 'HoraireCabinet')
    HoraireCabinet.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('rdv', '0008_service_image_url'),
    ]

    operations = [
        migrations.RunPython(set_horaires, reverse_horaires),
    ]
