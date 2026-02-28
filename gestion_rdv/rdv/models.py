from django.db import models
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
    def next_in_queue(self, user=None):
        """Return the next Rendez_vous object for the queue."""
        qs = self.filter(status='pending')
        if user is not None:
            profile = getattr(user, 'profile', None)
            if profile and profile.role != 'admin':
                qs = qs.filter(utilisateur=user)
        qs = qs.order_by(models.Case(models.When(priority='urgent', then=0), default=1), 'date', 'created_at')
        return qs.first()


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
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='rendez_vous')

    class Meta:
        ordering = ['-priority', 'date', 'created_at']

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
        ('admin', 'Admin'),
        ('agent', 'Agent'),
        ('user', 'User'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    nom = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Patient(models.Model):
    """Patient: représenté par User avec profil patient (id, nom)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')
    nom = models.CharField(max_length=150)

    class Meta:
        verbose_name = 'Patient'
        verbose_name_plural = 'Patients'

    def __str__(self):
        return self.nom or self.user.username


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
    )
    rendez_vous = models.OneToOneField(
        'Rendez_vous', on_delete=models.CASCADE, null=True, blank=True, related_name='ticket'
    )
    numero_ticket = models.PositiveIntegerField()
    priorite = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'File d\'attente'
        verbose_name_plural = 'Files d\'attente'
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
    if created:
        Utilisateur.objects.create(user=instance, nom=instance.get_full_name() or instance.username)
    else:
        Utilisateur.objects.get_or_create(user=instance)


@receiver(post_save, sender=Utilisateur)
def create_patient_for_user_role(sender, instance, **kwargs):
    """Crée Patient + Compte quand Utilisateur a rôle user."""
    if instance.role == 'user' and not Patient.objects.filter(user=instance.user).exists():
        patient = Patient.objects.create(user=instance.user, nom=instance.nom or instance.user.username)
        Compte.objects.create(patient=patient, solde=Decimal('0.00'))


def create_patient_for_user(user, nom=None):
    """Crée Patient et Compte pour un utilisateur (rôle user)."""
    patient, created = Patient.objects.get_or_create(user=user, defaults={'nom': nom or user.username})
    if created:
        Compte.objects.get_or_create(patient=patient, defaults={'solde': Decimal('0.00')})
    return patient


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
