# Generated manually for Service, CreneauHoraire, Rendez_vous.service

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rdv', '0004_alter_rendez_vous_options_rendez_vous_priority_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Service',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=150)),
                ('duree_minutes', models.PositiveIntegerField(default=30, help_text='Durée en minutes')),
                ('description', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Service',
                'verbose_name_plural': 'Services',
            },
        ),
        migrations.CreateModel(
            name='CreneauHoraire',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jour', models.PositiveSmallIntegerField(choices=[(0, 'Lundi'), (1, 'Mardi'), (2, 'Mercredi'), (3, 'Jeudi'), (4, 'Vendredi'), (5, 'Samedi'), (6, 'Dimanche')])),
                ('heure_debut', models.TimeField()),
                ('heure_fin', models.TimeField()),
                ('actif', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Créneau horaire',
                'verbose_name_plural': 'Créneaux horaires',
                'ordering': ['jour', 'heure_debut'],
            },
        ),
        migrations.AddField(
            model_name='rendez_vous',
            name='service',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rendez_vous', to='rdv.service'),
        ),
    ]
