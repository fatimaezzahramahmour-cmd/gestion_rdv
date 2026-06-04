import uuid

from django.db import models, transaction, IntegrityError
from django.contrib.auth.models import User
from decimal import Decimal


class Service(models.Model):
	"""Service proposé (ex: Consultation, Radiologie)."""
	nom = models.CharField(max_length=150)
	duree_minutes = models.PositiveIntegerField(default=30, help_text='Durée en minutes')
	description = models.TextField(blank=True)
	image_url = models.URLField(blank=True, help_text='URL image pour la carte "Notre travail"')

	class Meta:
		verbose_name = 'Service'
		verbose_name_plural = 'Services'

	def __str__(self):
		return self.nom


class HoraireCabinet(models.Model):
	"""HoraireCabinet: horaires d'ouverture du cabinet (jour, heureOuverture, heureFermeture)."""
	JOURS = [
		(0, 'Lundi'),
		(1, 'Mardi'),
		(2, 'Mercredi'),
		(3, 'Jeudi'),
		(4, 'Vendredi'),
		(5, 'Samedi'),
		(6, 'Dimanche'),
	]
	jour = models.PositiveSmallIntegerField(choices=JOURS)
	heure_ouverture = models.TimeField()
	heure_fermeture = models.TimeField()
	actif = models.BooleanField(default=True)

	class Meta:
		verbose_name = 'Horaire cabinet'
		verbose_name_plural = 'Horaires cabinet'
		ordering = ['jour', 'heure_ouverture']

	def __str__(self):
		return f"{self.get_jour_display()} {self.heure_ouverture} - {self.heure_fermeture}"


class CreneauHoraire(models.Model):
	"""Créneau horaire disponible (jour + plage horaire) - alias pour compatibilité."""
	JOURS = [
		(0, 'Lundi'),
		(1, 'Mardi'),
		(2, 'Mercredi'),
		(3, 'Jeudi'),
		(4, 'Vendredi'),
		(5, 'Samedi'),
		(6, 'Dimanche'),
	]
	jour = models.PositiveSmallIntegerField(choices=JOURS)
	heure_debut = models.TimeField()
	heure_fin = models.TimeField()
	actif = models.BooleanField(default=True)

	class Meta:
		verbose_name = 'Créneau horaire'
		verbose_name_plural = 'Créneaux horaires'
		ordering = ['jour', 'heure_debut']

	def __str__(self):
		return f"{self.get_jour_display()} {self.heure_debut} - {self.heure_fin}"


class RendezVousManager(models.Manager):
    def _queue_order(self, qs):
        return qs.order_by(
            models.Case(models.When(priority='urgent', then=0), default=1),
            'date',
            'created_at',
        )

    def next_in_queue(self, user=None):
        """Return the next Rendez_vous object for the queue."""
        qs = self.filter(status='pending')
        if user is not None:
            profile = getattr(user, 'profile', None)
            if profile and profile.role != 'admin':
                qs = qs.filter(utilisateur=user)
        return self._queue_order(qs).first()

    def next_in_queue_agent_global(self):
        """Prochain pending : d’abord les RDV dont la date est « aujourd’hui » au cabinet, sinon file globale."""
        from datetime import datetime, time, timedelta
        from django.conf import settings as dj_settings
        from django.utils import timezone as dj_tz
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(str(dj_settings.TIME_ZONE))
        today = dj_tz.localtime(dj_tz.now(), tz).date()
        start = datetime.combine(today, time.min, tzinfo=tz)
        end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
        qs = self.filter(status='pending')
        hit = self._queue_order(qs.filter(date__gte=start, date__lt=end)).first()
        if hit:
            return hit
        return self._queue_order(qs).first()


class Rendez_vous(models.Model):
    objects = RendezVousManager()

    titre = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateTimeField()
    utilisateur = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    )

    PRIORITY_CHOICES = (
        ('normal', 'Cas ordinaire'),
        ('urgent', 'Urgent'),
        ('control', 'Contrôle'),
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='rendez_vous')

    class Meta:
        ordering = ['-priority', 'date', 'created_at']
        verbose_name = 'Rendez-vous'
        verbose_name_plural = 'Rendez-vous'

    def __str__(self):
        return f"{self.titre} ({self.date:%Y-%m-%d %H:%M})"

    @property
    def queue_position(self):
        """Compute 1-based position in the pending queue (by priority desc then date asc)."""
        qs = Rendez_vous.objects.filter(status='pending')
        # map priority to numeric for ordering: urgent first
        ordered = sorted(qs, key=lambda r: (0 if r.priority == 'urgent' else 1, r.date, r.created_at))
        try:
            return ordered.index(self) + 1
        except ValueError:
            return None


class Utilisateur(models.Model):
    """Profile model linked to Django `User` to store role and display name (Agent/Admin)."""
    ROLE_CHOICES = (
        ('admin', 'Administrateur'),
        ('agent', 'Réception'),
        ('user', 'Patient'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    nom = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')

    class Meta:
        verbose_name = 'Compte'
        verbose_name_plural = 'Comptes'

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Patient(models.Model):
    """Patient: un enregistrement unique par utilisateur (id auto + référence UUID)."""
    reference = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text='Identifiant patient unique (UUID)',
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='patient_profile',
    )
    nom = models.CharField(max_length=150)

    class Meta:
        verbose_name = 'Patient'
        verbose_name_plural = 'Patients'

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = uuid.uuid4()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.nom or self.user.username} ({self.reference})'


class Compte(models.Model):
    """Compte: compte patient (solde) - composition avec Patient."""
    patient = models.OneToOneField(Patient, on_delete=models.CASCADE, related_name='compte')
    solde = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Compte'
        verbose_name_plural = 'Comptes'

    def __str__(self):
        return f"Compte {self.patient.nom} — {self.solde}"


class FileAttente(models.Model):
    """FileAttente: entrée dans la file d'attente (numeroTicket, priorite)."""
    PRIORITY_CHOICES = (
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),
        ('control', 'Contrôle'),
    )
    rendez_vous = models.OneToOneField(
        'Rendez_vous', on_delete=models.CASCADE, null=True, blank=True, related_name='ticket'
    )
    numero_ticket = models.PositiveIntegerField()
    priorite = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'File d\'attente'
        verbose_name_plural = 'File d\'attente'
        ordering = ['-priorite', 'numero_ticket']

    def __str__(self):
        return f"Ticket #{self.numero_ticket} ({self.priorite})"


class JourFermeture(models.Model):
    """Jours de fermeture du cabinet (config Admin)."""
    date = models.DateField(unique=True)
    motif = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'Jour de fermeture'
        verbose_name_plural = 'Jours de fermeture'
        ordering = ['date']

    def __str__(self):
        return f"{self.date} — {self.motif or 'Fermé'}"


from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Profil applicatif — get_or_create pour ne pas doubler avec l'admin (ajout compte)."""
    nom = (instance.get_full_name() or instance.username or '').strip()
    Utilisateur.objects.get_or_create(
        user=instance,
        defaults={'nom': nom, 'role': 'user'},
    )


@receiver(post_save, sender=Utilisateur)
def create_patient_for_user_role(sender, instance, **kwargs):
    """Crée Patient + Compte quand Utilisateur a rôle user (sans doublon)."""
    if instance.role == 'user':
        ensure_patient_for_user(instance.user, nom=instance.nom or instance.user.username)


def ensure_patient_for_user(user, nom=None):
    """
    Retourne le Patient unique lié à cet utilisateur.
    Thread-safe : une seule création même en cas d'appels simultanés.
    """
    display_nom = (nom or '').strip() or user.get_full_name().strip() or user.username

    with transaction.atomic():
        try:
            patient = Patient.objects.select_for_update().get(user=user)
            if nom and patient.nom != display_nom:
                patient.nom = display_nom
                patient.save(update_fields=['nom'])
        except Patient.DoesNotExist:
            try:
                patient = Patient.objects.create(
                    user=user,
                    nom=display_nom,
                    reference=uuid.uuid4(),
                )
            except IntegrityError:
                patient = Patient.objects.get(user=user)
        Compte.objects.get_or_create(
            patient=patient,
            defaults={'solde': Decimal('0.00')},
        )
        return patient


def create_patient_for_user(user, nom=None):
    """Alias rétrocompatible."""
    return ensure_patient_for_user(user, nom=nom)


class Conversation(models.Model):
    STATUT_CHOICES = [
        ('active', 'Active'),
        ('fermee', 'Fermée'),
        ('transferee', 'Transférée à un agent'),
    ]
    id = models.BigAutoField(primary_key=True)
    utilisateur = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='conversations'
    )
    session_id = models.CharField(max_length=100, db_index=True)
    sujet = models.CharField(max_length=200, blank=True, default='')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='active')
    contexte = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rdv_conversation'
        ordering = ['-updated_at']

    def __str__(self):
        user_label = self.utilisateur.email if self.utilisateur else f"Anonyme-{self.session_id[:8]}"
        return f"Conversation #{self.id} — {user_label}"

    @property
    def nombre_messages(self):
        return self.messages.count()


class MessageChatbot(models.Model):
    ROLE_CHOICES = [
        ('user', 'Utilisateur'),
        ('assistant', 'Assistant IA'),
        ('system', 'Système'),
        ('agent', 'Agent humain'),
    ]
    id = models.BigAutoField(primary_key=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    contenu = models.TextField()
    intention_detectee = models.CharField(max_length=50, blank=True, default='')
    confiance = models.FloatField(default=0.0)
    sources_utilisees = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rdv_message_chatbot'
        ordering = ['created_at']


class ActionChatbot(models.Model):
    nom = models.CharField(max_length=100)
    type_action = models.CharField(max_length=50, default='redirect')
    description = models.TextField(blank=True)
    url_cible = models.URLField(blank=True, null=True)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Action Chatbot'
        verbose_name_plural = 'Actions Chatbot'

    def __str__(self):
        return self.nom


class FAQDentaire(models.Model):
    question = models.CharField(max_length=255, unique=True)
    reponse = models.TextField()
    categorie = models.CharField(max_length=100, blank=True, default='general')
    mots_cles = models.CharField(max_length=500, blank=True, default='', help_text='Mots-clés séparés par des virgules')
    priorite = models.IntegerField(default=0, help_text="Ordre d'affichage (0 = normal, plus haut = prioritaire)")
    compteur_utilisation = models.PositiveIntegerField(default=0, help_text='Nombre de fois que cette FAQ a été utilisée')
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'FAQ Dentaire'
        verbose_name_plural = 'FAQ dentaires'
        ordering = ['-priorite', 'question']

    def __str__(self):
        return self.question

    def incrementer_usage(self):
        self.compteur_utilisation += 1
        self.save(update_fields=['compteur_utilisation'])


class Statistique:
    """Statistique: genererRapport, calculerNombreRendezVous."""
    @staticmethod
    def calculer_nombre_rendez_vous(filtre=None):
        qs = Rendez_vous.objects.all()
        if filtre:
            qs = qs.filter(**filtre)
        return qs.count()

    @staticmethod
    def generer_rapport(debut=None, fin=None):
        from django.db.models import Count
        qs = Rendez_vous.objects.all()
        if debut:
            qs = qs.filter(date__gte=debut)
        if fin:
            qs = qs.filter(date__lte=fin)
        by_status = qs.values('status').annotate(count=Count('id'))
        total = qs.count()
        urgent = qs.filter(priority='urgent').count()
        return {'total': total, 'urgent': urgent, 'by_status': list(by_status)}
