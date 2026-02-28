# Migration fix: Admin et Agent avec emails/mots de passe fixes

from django.db import migrations
from django.contrib.auth.hashers import make_password


def create_admin_and_agent(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Utilisateur = apps.get_model('rdv', 'Utilisateur')

    # Admin: admin@admin.com / admin123
    admin_user, created = User.objects.get_or_create(
        username='admin@admin.com',
        defaults={
            'email': 'admin@admin.com',
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
        }
    )
    if created:
        admin_user.password = make_password('admin123')
        admin_user.save()
        Utilisateur.objects.get_or_create(user=admin_user, defaults={'nom': 'Administrateur', 'role': 'admin'})
    else:
        admin_user.email = 'admin@admin.com'
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.password = make_password('admin123')
        admin_user.save()
        profile, _ = Utilisateur.objects.get_or_create(user=admin_user, defaults={'nom': 'Administrateur', 'role': 'admin'})
        if profile.role != 'admin':
            profile.role = 'admin'
            profile.save()

    # Agent: agent@agent.com / agent123
    agent_user, created = User.objects.get_or_create(
        username='agent@agent.com',
        defaults={
            'email': 'agent@agent.com',
            'is_staff': False,
            'is_superuser': False,
            'is_active': True,
        }
    )
    if created:
        agent_user.password = make_password('agent123')
        agent_user.save()
        Utilisateur.objects.get_or_create(user=agent_user, defaults={'nom': 'Agent', 'role': 'agent'})
    else:
        agent_user.email = 'agent@agent.com'
        agent_user.password = make_password('agent123')
        agent_user.save()
        profile, _ = Utilisateur.objects.get_or_create(user=agent_user, defaults={'nom': 'Agent', 'role': 'agent'})
        if profile.role != 'agent':
            profile.role = 'agent'
            profile.save()


def reverse_migration(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    User.objects.filter(username__in=['admin@admin.com', 'agent@agent.com']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('rdv', '0006_structure_diagramme_classe'),
    ]

    operations = [
        migrations.RunPython(create_admin_and_agent, reverse_migration),
    ]
