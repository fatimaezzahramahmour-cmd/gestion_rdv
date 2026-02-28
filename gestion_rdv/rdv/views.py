from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Utilisateur, Statistique, Service
from .forms import RendezVousForm
from .models import Rendez_vous
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta


def _is_agent(user):
	profile = getattr(user, 'profile', None)
	return profile and profile.role == 'agent' or getattr(user, 'is_staff', False)


def _queue_ordered():
	"""File d'attente : tous les RDV pending triés (urgent d'abord, puis date, created_at)."""
	qs = Rendez_vous.objects.filter(status='pending')
	return sorted(qs, key=lambda r: (0 if r.priority == 'urgent' else 1, r.date, r.created_at))


def _patient_display_name(user):
	"""Nom d'affichage pour un patient (sans email)."""
	try:
		nom = (getattr(user.patient_profile, 'nom', None) or '').strip()
		if nom:
			return nom
	except Exception:
		pass
	try:
		nom = (getattr(user.profile, 'nom', None) or '').strip()
		if nom:
			return nom
	except Exception:
		pass
	if user.first_name or user.last_name:
		return (user.get_full_name() or '').strip()
	return 'Patient'


def accueil(request):
	"""Page d'accueil publique : cabinet dentaire (khdma dyalna). Connexion en haut à droite."""
	services = Service.objects.all()[:8]
	return render(request, 'rdv/accueil.html', {'services': services})


@login_required
def agent_dashboard(request):
	"""Agent: RDV du jour, appeler prochain, valider/annuler."""
	if not _is_agent(request.user):
		return redirect('extranet')

	today = timezone.now().date()
	rdv_du_jour = Rendez_vous.objects.filter(date__date=today).exclude(status='cancelled').order_by('date')
	prochain = Rendez_vous.objects.next_in_queue(user=None)  # Global queue for agent

	context = {
		'rdv_du_jour': rdv_du_jour,
		'prochain': prochain,
	}
	return render(request, 'rdv/agent_dashboard.html', context)


@login_required
@require_POST
def agent_appeler_prochain(request):
	"""Appel du prochain ticket: afficher et marquer confirmé."""
	if not _is_agent(request.user):
		return redirect('extranet')
	next_obj = Rendez_vous.objects.next_in_queue(user=None)
	if next_obj:
		next_obj.status = 'confirmed'
		next_obj.save()
		messages.success(request, f'Ticket appelé: {next_obj.titre}')
	return redirect('agent_dashboard')


@login_required
@require_POST
def rdv_valider(request, pk):
	"""Valider un RDV (marquer comme done = passé chez le médecin)."""
	if not _is_agent(request.user):
		return redirect('extranet')
	rdv = get_object_or_404(Rendez_vous, pk=pk)
	rdv.status = 'done'
	rdv.save()
	messages.success(request, f'Passage chez le médecin enregistré pour "{rdv.titre}".')
	# Rester sur la page d'où on vient si c'est la file d'attente
	next_url = request.POST.get('next', '')
	if next_url == 'file_attente':
		return redirect('agent_file_attente')
	return redirect('agent_dashboard')


@login_required
@require_POST
def rdv_annuler(request, pk):
	"""Annuler un RDV."""
	if not _is_agent(request.user):
		return redirect('extranet')
	rdv = get_object_or_404(Rendez_vous, pk=pk)
	rdv.status = 'cancelled'
	rdv.save()
	messages.success(request, f'RDV "{rdv.titre}" annulé.')
	return redirect('agent_dashboard')


def login_view(request):
	if request.method == 'POST':
		email = request.POST.get('email')
		password = request.POST.get('password')
		# authenticate by username or email
		from django.contrib.auth.models import User
		username = None
		try:
			user = User.objects.get(email=email)
			username = user.username
		except User.DoesNotExist:
			# maybe the user used their email as username
			username = email

		# Try authenticate using resolved username
		user = authenticate(request, username=username, password=password)
		if user is None and username != email:
			# fallback: try authenticating with the raw email as username
			user = authenticate(request, username=email, password=password)

		if user is not None:
			login(request, user)
			profile = getattr(user, 'profile', None)
			role = profile.role if profile else 'user'
			if role == 'admin' or getattr(user, 'is_staff', False):
				return redirect('/admin/')  # Django Admin dashboard
			if role == 'agent':
				return redirect('agent_dashboard')
			return redirect('extranet')
		messages.error(request, 'Identifiants invalides. Si vous n\'avez pas de compte, créez-en un.')
	return render(request, 'rdv/login.html')


def logout_view(request):
	logout(request)
	return redirect('accueil')


@login_required
def extranet(request):
	profile = getattr(request.user, 'profile', None)
	role = profile.role if profile else 'user'
	return render(request, 'rdv/extranet.html', {'role': role})


@login_required
def rdv_list(request):
	# list rendez-vous for current user (admin sees all)
	profile = getattr(request.user, 'profile', None)
	if profile and profile.role == 'admin':
		items = Rendez_vous.objects.all().order_by('-date')
	else:
		items = Rendez_vous.objects.filter(utilisateur=request.user).order_by('-date')
	return render(request, 'rdv/list.html', {'items': items})


@login_required
def rdv_create(request):
	if request.method == 'POST':
		form = RendezVousForm(request.POST)
		if form.is_valid():
			rdv = form.save(commit=False)
			rdv.utilisateur = request.user
			rdv.save()
			messages.success(request, 'Rendez-vous créé')
			return redirect('rdv_list')
	else:
		form = RendezVousForm()
	return render(request, 'rdv/create.html', {'form': form})


@login_required
def rdv_next(request):
	"""Show next rendez-vous in queue (global for admin, per-user otherwise)."""
	next_obj = Rendez_vous.objects.next_in_queue(user=request.user)
	return render(request, 'rdv/next.html', {'next': next_obj})


@login_required
def file_attente_view(request):
	"""Page file d'attente : Patient numéro 1, 2, 3... avec position du patient connecté."""
	queue = _queue_ordered()
	queue_entries = []
	for i, rdv in enumerate(queue, 1):
		nom = _patient_display_name(rdv.utilisateur)
		is_me = rdv.utilisateur_id == request.user.id
		queue_entries.append({
			'rdv': rdv,
			'position': i,
			'label': 'Vous' if is_me else nom,
			'is_me': is_me,
		})
	return render(request, 'rdv/file_attente.html', {'queue_entries': queue_entries})


@login_required
def agent_file_attente_view(request):
	"""File d'attente pour l'agent : Patient numéro 1, 2, 3... + confirmer passage chez le médecin."""
	if not _is_agent(request.user):
		return redirect('extranet')
	queue = _queue_ordered()
	queue_entries = []
	for i, rdv in enumerate(queue, 1):
		nom = _patient_display_name(rdv.utilisateur)
		queue_entries.append({
			'rdv': rdv,
			'position': i,
			'label': nom,
		})
	return render(request, 'rdv/agent_file_attente.html', {'queue_entries': queue_entries})


@staff_member_required
def admin_dashboard(request):
	"""Admin dashboard - Statistique.generer_rapport, superviser RDV."""
	now = timezone.now()
	next_week = now + timedelta(days=7)

	rapport = Statistique.generer_rapport()
	total = rapport['total']
	urgent_count = rapport['urgent']
	by_status = rapport['by_status']
	upcoming = Rendez_vous.objects.filter(date__gte=now, date__lte=next_week).order_by('date')[:10]

	context = {
		'total': total,
		'by_status': by_status,
		'urgent_count': urgent_count,
		'upcoming': upcoming,
	}
	return render(request, 'rdv/admin_dashboard.html', context)


def signup_view(request):
	"""Simple signup to create a user with a role (admin/agent/user)."""
	from django.contrib.auth.models import User
	if request.method == 'POST':
		email = request.POST.get('email')
		password1 = request.POST.get('password1')
		password2 = request.POST.get('password2')
		# Signup only creates regular user accounts; admin/agent are fixed by admin scripts
		role = 'user'

		if not email or not password1:
			messages.error(request, 'Email et mot de passe requis')
			return render(request, 'rdv/signup.html')
		if password1 != password2:
			messages.error(request, 'Les mots de passe ne correspondent pas')
			return render(request, 'rdv/signup.html')

		if User.objects.filter(email=email).exists():
			messages.info(request, 'Un compte avec cet email existe déjà. Connectez-vous.')
			return redirect('login')

		# Use email as username to avoid collisions
		user = User.objects.create_user(username=email, email=email, password=password1)
		# ensure profile exists (signal in models.py should create it)
		profile = getattr(user, 'profile', None)
		if profile:
			profile.role = role
			profile.save()

		login(request, user)
		if role == 'admin':
			return redirect('admin_dashboard')
		return redirect('extranet')
	return render(request, 'rdv/signup.html')
