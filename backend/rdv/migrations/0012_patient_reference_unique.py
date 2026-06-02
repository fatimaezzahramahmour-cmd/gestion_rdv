import uuid

from django.db import migrations, models


def assign_patient_references(apps, schema_editor):
    Patient = apps.get_model('rdv', 'Patient')
    for patient in Patient.objects.filter(reference__isnull=True):
        patient.reference = uuid.uuid4()
        patient.save(update_fields=['reference'])


class Migration(migrations.Migration):

    dependencies = [
        ('rdv', '0011_chatbot_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='reference',
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                help_text='Identifiant patient unique (UUID)',
                null=True,
            ),
        ),
        migrations.RunPython(assign_patient_references, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='patient',
            name='reference',
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                help_text='Identifiant patient unique (UUID)',
                unique=True,
            ),
        ),
    ]
