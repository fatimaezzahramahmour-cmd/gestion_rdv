from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Utilisateur, Statistique, Service
from .forms import (
    RendezVousForm,
    get_creneaux_for_date,
    get_creneaux_table_semaine,
    patient_peut_modifier_ou_annuler,
    cabinet_local_today,
    cabinet_day_datetime_bounds,
)
from .models import Rendez_vous, FileAttente
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.utils import timezone
from django.conf import settings as dj_settings
from zoneinfo import ZoneInfo
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

	today = cabinet_local_today()
	start_day, end_day = cabinet_day_datetime_bounds(today)
	rdv_du_jour = (
		Rendez_vous.objects.filter(date__gte=start_day, date__lt=end_day)
		.exclude(status='cancelled')
		.order_by('date')
	)
	prochain = Rendez_vous.objects.next_in_queue_agent_global()
	en_attente_count = Rendez_vous.objects.filter(status='pending').count()

	rdv_du_jour_with_names = [{'rdv': r, 'patient_name': _patient_display_name(r.utilisateur) or r.utilisateur.username} for r in rdv_du_jour]
	prochain_name = _patient_display_name(prochain.utilisateur) if prochain else None
	tz_cab = ZoneInfo(str(dj_settings.TIME_ZONE))
	prochain_date_cabinet = (
		timezone.localtime(prochain.date, tz_cab).date() if prochain else None
	)
	prochain_pas_aujourdhui = bool(
		prochain and prochain_date_cabinet and prochain_date_cabinet != today
	)

	context = {
		'rdv_du_jour': rdv_du_jour_with_names,
		'rdv_du_jour_list': rdv_du_jour,
		'prochain': prochain,
		'prochain_name': prochain_name,
		'count_rdv_jour': rdv_du_jour.count(),
		'en_attente_count': en_attente_count,
		'date_jour_label': today.strftime('%d/%m/%Y'),
		'prochain_pas_aujourdhui': prochain_pas_aujourdhui,
	}
	return render(request, 'rdv/agent_dashboard.html', context)


@login_required
@require_POST
def agent_appeler_prochain(request):
	"""Appel du prochain ticket: afficher et marquer confirmé."""
	if not _is_agent(request.user):
		return redirect('extranet')
	next_obj = Rendez_vous.objects.next_in_queue_agent_global()
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
	display = ''
	try:
		display = (getattr(request.user.patient_profile, 'nom', None) or '').strip()
	except Exception:
		pass
	if not display and profile and getattr(profile, 'nom', None):
		display = (profile.nom or '').strip()
	if not display:
		display = (request.user.get_full_name() or '').strip()
	return render(request, 'rdv/extranet.html', {'role': role, 'user_display_name': display})


@login_required
def rdv_list(request):
	profile = getattr(request.user, 'profile', None)
	if profile and profile.role == 'admin':
		items = Rendez_vous.objects.all().order_by('-date')
		item_rows = [{'rdv': r, 'peut_gerer': False} for r in items]
	else:
		items = Rendez_vous.objects.filter(utilisateur=request.user).order_by('-date')
		item_rows = [{'rdv': r, 'peut_gerer': patient_peut_modifier_ou_annuler(r)} for r in items]
	return render(request, 'rdv/list.html', {'items': items, 'item_rows': item_rows})


@login_required
@login_required
@require_GET
def rdv_creneaux_api(request):
	"""Retourne les créneaux disponibles pour une date (GET ?date=YYYY-MM-DD)."""
	date_str = request.GET.get('date', '')
	if not date_str:
		return JsonResponse({'creneaux': []})
	creneaux = get_creneaux_for_date(date_str)
	return JsonResponse({'creneaux': creneaux})


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
	creneaux_table = get_creneaux_table_semaine()
	now = timezone.now()
	return render(
		request,
		'rdv/create.html',
		{
			'form': form,
			'creneaux_table': creneaux_table,
			'booking_server_now_ms': int(now.timestamp() * 1000),
			'edit_mode': False,
		},
	)


@login_required
@require_POST
def rdv_patient_annuler(request, pk):
	profile = getattr(request.user, 'profile', None)
	if profile and profile.role in ('agent', 'admin'):
		messages.error(request, 'Utilisez l’espace réception pour gérer les rendez-vous.')
		return redirect('extranet')
	rdv = get_object_or_404(Rendez_vous, pk=pk, utilisateur=request.user)
	if not patient_peut_modifier_ou_annuler(rdv):
		messages.error(
			request,
			'Annulation impossible : il faut au moins 24 h avant le rendez-vous, ou le RDV est déjà terminé / annulé.',
		)
		return redirect('rdv_list')
	FileAttente.objects.filter(rendez_vous=rdv).delete()
	rdv.status = 'cancelled'
	rdv.save()
	messages.success(request, 'Votre rendez-vous a été annulé.')
	return redirect('rdv_list')


@login_required
def rdv_patient_modifier(request, pk):
	from datetime import datetime as dt_module

	profile = getattr(request.user, 'profile', None)
	if profile and profile.role in ('agent', 'admin'):
		messages.error(request, 'Action réservée aux patients.')
		return redirect('extranet')
	rdv = get_object_or_404(Rendez_vous, pk=pk, utilisateur=request.user)
	if not patient_peut_modifier_ou_annuler(rdv):
		messages.error(
			request,
			'Modification impossible : au moins 24 h avant le rendez-vous sont nécessaires.',
		)
		return redirect('rdv_list')
	if request.method == 'POST':
		form = RendezVousForm(request.POST, instance=rdv, exclude_rdv_pk=rdv.pk)
		if form.is_valid():
			form.save()
			messages.success(request, 'Votre rendez-vous a été modifié.')
			return redirect('rdv_list')
	else:
		form = RendezVousForm(instance=rdv, exclude_rdv_pk=rdv.pk)
	creneaux_table = get_creneaux_table_semaine(
		exclude_rdv_pk=rdv.pk,
		extra_dates=[timezone.localtime(rdv.date).date()],
	)
	now = timezone.now()
	iso = request.POST.get('date') if request.method == 'POST' else rdv.date.isoformat()
	if not iso:
		iso = rdv.date.isoformat()
	try:
		parsed = dt_module.fromisoformat(iso.replace('Z', '+00:00'))
		if timezone.is_naive(parsed):
			parsed = timezone.make_aware(parsed)
		rdv_slot_label = timezone.localtime(parsed).strftime('%d/%m/%Y — %H:%M')
	except Exception:
		rdv_slot_label = timezone.localtime(rdv.date).strftime('%d/%m/%Y — %H:%M')
	return render(
		request,
		'rdv/create.html',
		{
			'form': form,
			'creneaux_table': creneaux_table,
			'booking_server_now_ms': int(now.timestamp() * 1000),
			'edit_mode': True,
			'rdv_initial_iso': iso,
			'rdv_slot_label': rdv_slot_label,
		},
	)


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
	"""Simple signup to create a user with a role (admin/agent/user). Prénom et Nom pour le message Bienvenue."""
	from django.contrib.auth.models import User
	if request.method == 'POST':
		first_name = (request.POST.get('first_name') or '').strip()
		last_name = (request.POST.get('last_name') or '').strip()
		email = request.POST.get('email')
		password1 = request.POST.get('password1')
		password2 = request.POST.get('password2')
		role = 'user'

		if not email or not password1:
			messages.error(request, 'Email et mot de passe requis')
			return render(request, 'rdv/signup.html')
		if not first_name or not last_name:
			messages.error(request, 'Prénom et nom requis')
			return render(request, 'rdv/signup.html')
		if password1 != password2:
			messages.error(request, 'Les mots de passe ne correspondent pas')
			return render(request, 'rdv/signup.html')

		if User.objects.filter(email=email).exists():
			messages.info(request, 'Un compte avec cet email existe déjà. Connectez-vous.')
			return redirect('login')

		user = User.objects.create_user(
			username=email, email=email, password=password1,
			first_name=first_name, last_name=last_name
		)
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
