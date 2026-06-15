from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from .models import Utilisateur, Statistique, Service
from .forms import (
    RendezVousForm,
    get_creneaux_for_date,
    get_creneaux_table_semaine,
    patient_peut_modifier_ou_annuler,
    agent_peut_appeler_rdv,
    agent_peut_confirmer_passage,
    agent_message_si_appeler_indisponible,
    agent_message_si_passage_indisponible,
    cabinet_local_today,
    cabinet_day_datetime_bounds,
    rdv_datetime_cabinet,
)
from .models import Rendez_vous, FileAttente
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.utils import timezone
from django.conf import settings as dj_settings
from zoneinfo import ZoneInfo
from datetime import timedelta


def _is_admin(user):
	profile = getattr(user, 'profile', None)
	return bool(profile and profile.role == 'admin')


def _is_agent(user):
	"""True uniquement si role=agent ; is_staff seul ne donne pas accès à /agent/*."""
	if not user.is_authenticated:
		return False
	profile = getattr(user, 'profile', None)
	return bool(profile and profile.role == 'agent')


def _redirect_non_patient(request):
	"""Redirige admin/agent hors de l'espace patient."""
	if _is_admin(request.user):
		return redirect('/admin/')
	if _is_agent(request.user):
		return redirect('agent_dashboard')
	return None


def _redirect_non_agent(request):
	"""Redirige hors de l'espace agent si role≠agent (admin/staff → /admin/)."""
	if _is_agent(request.user):
		return None
	if _is_admin(request.user) or request.user.is_staff:
		return redirect('/admin/')
	return redirect('extranet')


def _pending_queue_for_day(day):
	"""RDV pending du jour `day`, triés (urgent d'abord, puis date, created_at)."""
	qs = _pending_for_day(day)
	return sorted(qs, key=lambda r: (0 if r.priority == 'urgent' else 1, r.date, r.created_at))


def _queue_ordered():
	"""File d'attente : tous les RDV pending triés (urgent d'abord, puis date, created_at)."""
	qs = Rendez_vous.objects.filter(status='pending')
	return sorted(qs, key=lambda r: (0 if r.priority == 'urgent' else 1, r.date, r.created_at))


def _pending_for_day(day):
	"""RDV pending dont la date tombe le jour `day` (fuseau cabinet)."""
	start_day, end_day = cabinet_day_datetime_bounds(day)
	return Rendez_vous.objects.filter(
		status='pending',
		date__gte=start_day,
		date__lt=end_day,
	)


def _rdv_du_jour_queryset(day):
	"""RDV du jour non annulés (fuseau cabinet)."""
	start_day, end_day = cabinet_day_datetime_bounds(day)
	return (
		Rendez_vous.objects.filter(date__gte=start_day, date__lt=end_day)
		.exclude(status='cancelled')
		.order_by('date')
	)


def _confirmed_ordered():
	"""Patients appelés (confirmed), même ordre de priorité."""
	qs = Rendez_vous.objects.filter(status='confirmed')
	return sorted(qs, key=lambda r: (0 if r.priority == 'urgent' else 1, r.date, r.created_at))


def _confirmed_for_day(day):
	"""Patients appelés (confirmed) dont le RDV tombe le jour `day`."""
	start_day, end_day = cabinet_day_datetime_bounds(day)
	qs = Rendez_vous.objects.filter(
		status='confirmed',
		date__gte=start_day,
		date__lt=end_day,
	)
	return sorted(qs, key=lambda r: (0 if r.priority == 'urgent' else 1, r.date, r.created_at))


def _user_has_rdv_on_day(user, day):
	"""True si le patient a un RDV pending ou confirmed ce jour-là."""
	start_day, end_day = cabinet_day_datetime_bounds(day)
	return Rendez_vous.objects.filter(
		utilisateur=user,
		status__in=('pending', 'confirmed'),
		date__gte=start_day,
		date__lt=end_day,
	).exists()


def _patient_queue_day(user):
	"""
	Jour de file à afficher pour le patient :
	prochain RDV pending/confirmed (aujourd'hui ou futur), dès la réservation.
	"""
	today = cabinet_local_today()
	start_today, end_today = cabinet_day_datetime_bounds(today)

	if Rendez_vous.objects.filter(
		utilisateur=user,
		status='confirmed',
		date__gte=start_today,
		date__lt=end_today,
	).exists():
		return today

	next_rdv = Rendez_vous.objects.filter(
		utilisateur=user,
		status__in=('pending', 'confirmed'),
		date__gte=start_today,
	).order_by('date').first()
	if next_rdv:
		return rdv_datetime_cabinet(next_rdv).date()
	return None


def _patient_queue_entries(user, queue_day):
	"""File du jour pour le patient : tous les pending anonymisés + statut appelé."""
	start_day, end_day = cabinet_day_datetime_bounds(queue_day)
	queue_entries = []
	patients_ahead = 0
	user_position = None

	confirmed_rdv = Rendez_vous.objects.filter(
		utilisateur=user,
		status='confirmed',
		date__gte=start_day,
		date__lt=end_day,
	).order_by('date').first()
	if confirmed_rdv:
		queue_entries.append({
			'rdv': confirmed_rdv,
			'position': None,
			'label': 'Vous êtes appelé(e)',
			'is_me': True,
			'is_called': True,
		})

	for i, rdv in enumerate(_pending_queue_for_day(queue_day), 1):
		is_me = rdv.utilisateur_id == user.id
		if is_me:
			user_position = i
			patients_ahead = i - 1
		queue_entries.append({
			'rdv': rdv,
			'position': i,
			'label': 'Vous' if is_me else f'Patient n°{i}',
			'is_me': is_me,
			'is_called': False,
		})

	return {
		'queue_entries': queue_entries,
		'patients_ahead': patients_ahead,
		'user_position': user_position,
	}


def _agent_redirect_after_action(request, default='agent_dashboard'):
	next_url = request.POST.get('next', '')
	if next_url == 'file_attente':
		return redirect('agent_file_attente')
	return redirect(default)


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
	redirect_resp = _redirect_non_agent(request)
	if redirect_resp:
		return redirect_resp

	today = cabinet_local_today()
	rdv_du_jour = _rdv_du_jour_queryset(today)
	prochain = Rendez_vous.objects.next_in_queue_agent_global()
	en_attente_aujourdhui_count = _pending_for_day(today).count()
	en_attente_total_count = Rendez_vous.objects.filter(status='pending').count()
	start_day, end_day = cabinet_day_datetime_bounds(today)
	appelles_aujourdhui_count = Rendez_vous.objects.filter(
		status='confirmed',
		date__gte=start_day,
		date__lt=end_day,
	).count()

	rdv_du_jour_with_names = []
	for r in rdv_du_jour:
		rdv_du_jour_with_names.append({
			'rdv': r,
			'patient_name': _patient_display_name(r.utilisateur) or r.utilisateur.username,
			'peut_appeler': agent_peut_appeler_rdv(r),
			'peut_confirmer': agent_peut_confirmer_passage(r),
			'msg_appeler': agent_message_si_appeler_indisponible(r),
			'msg_confirmer': agent_message_si_passage_indisponible(r),
		})
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
		'en_attente_aujourdhui_count': en_attente_aujourdhui_count,
		'en_attente_total_count': en_attente_total_count,
		'appelles_aujourdhui_count': appelles_aujourdhui_count,
		'date_jour_label': today.strftime('%d/%m/%Y'),
		'prochain_pas_aujourdhui': prochain_pas_aujourdhui,
		'prochain_peut_appeler': agent_peut_appeler_rdv(prochain) if prochain else False,
		'prochain_msg_appeler': agent_message_si_appeler_indisponible(prochain) if prochain else None,
	}
	return render(request, 'rdv/agent_dashboard.html', context)


@login_required
@require_POST
def agent_appeler_prochain(request):
	"""Appel du prochain patient : pending → confirmed."""
	redirect_resp = _redirect_non_agent(request)
	if redirect_resp:
		return redirect_resp
	next_obj = Rendez_vous.objects.next_in_queue_agent_global()
	if next_obj:
		if next_obj.status != 'pending':
			messages.error(request, 'Ce rendez-vous ne peut plus être appelé.')
			return redirect('agent_dashboard')
		if not agent_peut_appeler_rdv(next_obj):
			msg = agent_message_si_appeler_indisponible(next_obj)
			messages.error(request, msg or 'Appel non autorisé pour ce rendez-vous.')
			return redirect('agent_dashboard')
		next_obj.status = 'confirmed'
		next_obj.save()
		nom = _patient_display_name(next_obj.utilisateur) or next_obj.utilisateur.username
		messages.success(
			request,
			f'Patient appelé : {nom}. '
			f'Confirmez le passage chez le médecin une fois le patient reçu.',
		)
	else:
		messages.info(request, 'Aucun patient en attente dans la file.')
	return redirect('agent_dashboard')


@login_required
@require_POST
def agent_appeler_rdv(request, pk):
	"""Appeler un patient précis : pending → confirmed."""
	redirect_resp = _redirect_non_agent(request)
	if redirect_resp:
		return redirect_resp
	rdv = get_object_or_404(Rendez_vous, pk=pk)
	if rdv.status != 'pending':
		messages.error(
			request,
			'Seuls les rendez-vous « En attente » peuvent être appelés. '
			'Utilisez « Confirmer passage chez le médecin » si le patient est déjà appelé.',
		)
		return _agent_redirect_after_action(request)
	if not agent_peut_appeler_rdv(rdv):
		msg = agent_message_si_appeler_indisponible(rdv)
		messages.error(request, msg or 'Appel non autorisé pour ce rendez-vous.')
		return _agent_redirect_after_action(request)
	rdv.status = 'confirmed'
	rdv.save()
	nom = _patient_display_name(rdv.utilisateur) or rdv.utilisateur.username
	messages.success(
		request,
		f'Patient appelé : {nom}. '
		f'Confirmez le passage chez le médecin une fois le patient reçu.',
	)
	return _agent_redirect_after_action(request)


@login_required
@require_POST
def rdv_valider(request, pk):
	"""Confirmer passage chez le médecin : confirmed → done uniquement."""
	redirect_resp = _redirect_non_agent(request)
	if redirect_resp:
		return redirect_resp
	rdv = get_object_or_404(Rendez_vous, pk=pk)
	if rdv.status != 'confirmed':
		messages.error(
			request,
			'Appelez d\'abord le patient avant de confirmer le passage chez le médecin.',
		)
		return _agent_redirect_after_action(request)
	if not agent_peut_confirmer_passage(rdv):
		msg = agent_message_si_passage_indisponible(rdv)
		messages.error(
			request,
			msg or 'Le passage chez le médecin n\'est pas encore autorisé pour ce rendez-vous.',
		)
		return _agent_redirect_after_action(request)
	rdv.status = 'done'
	rdv.save()
	nom = _patient_display_name(rdv.utilisateur) or rdv.utilisateur.username
	messages.success(request, f'Passage chez le médecin enregistré pour {nom}.')
	return _agent_redirect_after_action(request)


@login_required
@require_POST
def rdv_annuler(request, pk):
	"""Annuler un RDV."""
	redirect_resp = _redirect_non_agent(request)
	if redirect_resp:
		return redirect_resp
	rdv = get_object_or_404(Rendez_vous, pk=pk)
	rdv.status = 'cancelled'
	rdv.save()
	messages.success(request, f'RDV "{rdv.titre}" annulé.')
	return redirect('agent_dashboard')


@ensure_csrf_cookie
@never_cache
@csrf_protect
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
			if role == 'admin':
				return redirect('/admin/')
			if role == 'agent':
				return redirect('agent_dashboard')
			return redirect('extranet')
		messages.error(request, 'Identifiants invalides.')
	return render(request, 'rdv/login.html')


def logout_view(request):
	logout(request)
	return redirect('accueil')


def csrf_failure(request, reason=''):
	"""Redirection friendly si token CSRF expiré (recharger la page login)."""
	messages.error(
		request,
		'Session expirée ou formulaire trop ancien. Rechargez la page de connexion et réessayez.',
	)
	return redirect('login')


@login_required
def extranet(request):
	redirect_resp = _redirect_non_patient(request)
	if redirect_resp:
		return redirect_resp

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

	now = timezone.now()
	mes_rdvs = Rendez_vous.objects.filter(utilisateur=request.user).order_by('-date')
	rdv_a_venir = mes_rdvs.filter(
		date__gte=now,
		status__in=('pending', 'confirmed'),
	).order_by('date').first()

	ma_position = None
	for i, rdv in enumerate(_queue_ordered(), 1):
		if rdv.utilisateur_id == request.user.id:
			ma_position = i
			break

	return render(request, 'rdv/extranet.html', {
		'role': role,
		'user_display_name': display,
		'mes_rdvs': mes_rdvs[:5],
		'rdv_a_venir': rdv_a_venir,
		'ma_position': ma_position,
	})


@login_required
def rdv_list(request):
	redirect_resp = _redirect_non_patient(request)
	if redirect_resp:
		return redirect_resp

	items = Rendez_vous.objects.filter(utilisateur=request.user).order_by('-date')
	item_rows = [
		{'rdv': r, 'peut_gerer': patient_peut_modifier_ou_annuler(r)}
		for r in items
	]
	return render(request, 'rdv/list.html', {'items': items, 'item_rows': item_rows})


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
	redirect_resp = _redirect_non_patient(request)
	if redirect_resp:
		return redirect_resp

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
	if profile and profile.role == 'admin':
		messages.info(request, 'La gestion des rendez-vous est réservée à la réception.')
		return redirect('/admin/')
	if profile and profile.role == 'agent':
		messages.error(request, 'Utilisez l’espace réception pour gérer les rendez-vous.')
		return redirect('agent_dashboard')
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
	if profile and profile.role == 'admin':
		messages.info(request, 'La modification des rendez-vous est réservée aux patients.')
		return redirect('/admin/')
	if profile and profile.role == 'agent':
		messages.error(request, 'Action réservée aux patients.')
		return redirect('agent_dashboard')
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
	"""Prochain RDV en attente du patient connecté."""
	redirect_resp = _redirect_non_patient(request)
	if redirect_resp:
		return redirect_resp

	next_obj = Rendez_vous.objects.next_in_queue(user=request.user)
	return render(request, 'rdv/next.html', {'next': next_obj})


@login_required
def file_attente_view(request):
	"""File d'attente patient : file du jour du RDV (dès la réservation)."""
	redirect_resp = _redirect_non_patient(request)
	if redirect_resp:
		return redirect_resp

	today = cabinet_local_today()
	queue_day = _patient_queue_day(request.user)

	if not queue_day:
		return render(request, 'rdv/file_attente.html', {
			'queue_entries': [],
			'queue_day': today,
			'show_queue': False,
			'queue_day_is_today': True,
			'patients_ahead': 0,
			'user_position': None,
		})

	data = _patient_queue_entries(request.user, queue_day)
	return render(request, 'rdv/file_attente.html', {
		'queue_entries': data['queue_entries'],
		'queue_day': queue_day,
		'show_queue': True,
		'queue_day_is_today': queue_day == today,
		'patients_ahead': data['patients_ahead'],
		'user_position': data['user_position'],
	})


@login_required
def agent_file_attente_view(request):
	"""File d'attente agent : pending (appeler) + confirmed (confirmer passage)."""
	redirect_resp = _redirect_non_agent(request)
	if redirect_resp:
		return redirect_resp
	queue_day = cabinet_local_today()
	pending_entries = []
	for i, rdv in enumerate(_pending_queue_for_day(queue_day), 1):
		nom = _patient_display_name(rdv.utilisateur)
		pending_entries.append({
			'rdv': rdv,
			'position': i,
			'label': nom,
			'peut_appeler': agent_peut_appeler_rdv(rdv),
			'msg_appeler': agent_message_si_appeler_indisponible(rdv),
		})
	called_entries = []
	for rdv in _confirmed_for_day(queue_day):
		nom = _patient_display_name(rdv.utilisateur)
		called_entries.append({
			'rdv': rdv,
			'label': nom,
			'peut_confirmer': agent_peut_confirmer_passage(rdv),
			'msg_confirmer': agent_message_si_passage_indisponible(rdv),
		})
	return render(request, 'rdv/agent_file_attente.html', {
		'pending_entries': pending_entries,
		'called_entries': called_entries,
	})


@staff_member_required
def admin_dashboard(request):
	"""Ancienne vue stats — redirige vers le tableau de bord Django admin."""
	return redirect('/admin/')


def signup_view(request):
	"""Inscription publique désactivée — extranet fermé, comptes créés par l'admin uniquement."""
	messages.info(
		request,
		"L'inscription en ligne est fermée. Connectez-vous avec vos identifiants "
		"ou contactez le cabinet pour obtenir un accès.",
	)
	return redirect('login')
