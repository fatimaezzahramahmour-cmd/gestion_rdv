from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Rendez_vous, JourFermeture

_TZ_CABINET = ZoneInfo(str(settings.TIME_ZONE))


def cabinet_local_today():
    """Date civile « aujourd’hui » au fuseau du cabinet (aligné sur les créneaux RDV)."""
    return timezone.localtime(timezone.now(), _TZ_CABINET).date()


def cabinet_day_datetime_bounds(dte):
    """Début (inclus) et fin (exclu) du jour `dte` au fuseau cabinet, pour filtrer les RDV."""
    start = datetime.combine(dte, time.min, tzinfo=_TZ_CABINET)
    end = datetime.combine(dte + timedelta(days=1), time.min, tzinfo=_TZ_CABINET)
    return start, end


def _instant_creneau(dte, t_hm):
    """Date + heure locale cabinet → datetime aware (comparable à timezone.now())."""
    return datetime.combine(dte, t_hm, tzinfo=_TZ_CABINET)


def _maintenant_utc():
    return timezone.now()


# Délai minimum avant le RDV pour annuler / modifier (patient)
DELAI_PATIENT_MODIFICATION_HEURES = 24


def patient_peut_modifier_ou_annuler(rdv):
    """True si le patient peut encore annuler ou changer ce RDV (≥ 24 h avant)."""
    if rdv.status in ('done', 'cancelled'):
        return False
    if rdv.status not in ('pending', 'confirmed'):
        return False
    limite = _maintenant_utc() + timedelta(hours=DELAI_PATIENT_MODIFICATION_HEURES)
    return rdv.date > limite

JOURS_NOMS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

# Horaires de RDV (~50 min) — matin puis après-midi
CRENEAUX_MATIN = [
    time(8, 0),
    time(8, 50),
    time(9, 40),
    time(10, 30),
    time(11, 20),
    time(12, 10),
]
CRENEAUX_APRES = [
    time(14, 0),
    time(14, 50),
    time(15, 40),
    time(16, 30),
    time(17, 20),
]
# Lundi → jeudi + mercredi : journée 8h → ~17h50 (dernier RDV 17h20)
CRENEAUX_JOUR_COMPLET = CRENEAUX_MATIN + CRENEAUX_APRES
# Vendredi : matin seulement (8h → 12h10)


def heures_pour_jour_semaine(weekday):
    """
    Lun, mar, mer, jeu : journée complète (matin + après-midi). Ven : matin seulement. Sam–dim : fermé.
    """
    if weekday in (5, 6):
        return []
    if weekday == 4:
        return list(CRENEAUX_MATIN)
    return list(CRENEAUX_JOUR_COMPLET)


def _time_key(t):
    return (t.hour, t.minute)


def _cinq_prochains_jours_ouvres(depuis):
    """5 prochains jours lun–ven à partir de `depuis` (inclus si jour ouvré)."""
    out = []
    d = depuis
    for _ in range(21):
        if d.weekday() < 5:
            out.append(d)
            if len(out) >= 5:
                break
        d += timedelta(days=1)
    return out


def est_creneau_horaire_officiel(dt):
    """True si la datetime (aware) correspond à un créneau autorisé."""
    local = timezone.localtime(dt)
    dte = local.date()
    t = time(local.hour, local.minute)
    return t in heures_pour_jour_semaine(dte.weekday())


def _rdv_occupe_slot(slot_dt, exclude_pk=None):
    qs = Rendez_vous.objects.filter(date=slot_dt).exclude(status='cancelled')
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def get_creneaux_disponibles(exclude_rdv_pk=None):
    """Liste (value iso, label) — créneaux fixes, pas déjà pris (sauf RDV exclude_rdv_pk)."""
    start_date = timezone.localtime(_maintenant_utc(), _TZ_CABINET).date()
    now = _maintenant_utc()
    choices = []
    for d in range(28):
        dte = start_date + timedelta(days=d)
        if JourFermeture.objects.filter(date=dte).exists():
            continue
        ws = dte.weekday()
        for t in heures_pour_jour_semaine(ws):
            slot_dt = _instant_creneau(dte, t)
            if slot_dt <= now:
                continue
            if not _rdv_occupe_slot(slot_dt, exclude_rdv_pk):
                label = f"{JOURS_NOMS[ws]} {dte:%d/%m/%Y} à {t:%H:%M}"
                choices.append((slot_dt.isoformat(), label))
    return choices[:200]


def get_creneaux_par_jour():
    flat = get_creneaux_disponibles()
    from collections import OrderedDict

    by_day = OrderedDict()
    for value, label in flat:
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            dte = timezone.localtime(dt).date()
            date_key = dte.isoformat()
            date_label = label.split(' à ')[0].strip() if ' à ' in label else str(dte)
            time_label = label.split(' à ')[-1].strip() if ' à ' in label else label
            if date_key not in by_day:
                by_day[date_key] = {'date_label': date_label, 'slots': []}
            by_day[date_key]['slots'].append({'value': value, 'label': time_label})
        except Exception:
            pass
    return [by_day[k] for k in sorted(by_day.keys())]


def get_creneaux_table_semaine(exclude_rdv_pk=None, extra_dates=None):
    """Jours ouvrés : 5 prochains + dates supplémentaires (ex. date du RDV modifié)."""
    now = _maintenant_utc()
    today = timezone.localtime(now, _TZ_CABINET).date()
    if today.weekday() >= 5:
        anchor = today + timedelta(days=7 - today.weekday())
    else:
        anchor = today
    day_set = set(_cinq_prochains_jours_ouvres(anchor))
    if extra_dates:
        for ed in extra_dates:
            if isinstance(ed, datetime):
                ed = ed.date()
            if ed.weekday() < 5 and ed >= today:
                day_set.add(ed)
    day_list = sorted(day_set)

    all_times_ordered = sorted(CRENEAUX_JOUR_COMPLET, key=_time_key)
    days = []
    allowed_per_col = []
    for dte in day_list:
        ferme = JourFermeture.objects.filter(date=dte).exists()
        days.append({
            'label': JOURS_NOMS[dte.weekday()],
            'date': dte.strftime('%d/%m/%Y'),
            'date_iso': dte.isoformat(),
            'ferme': ferme,
        })
        allowed_per_col.append(set(heures_pour_jour_semaine(dte.weekday())))

    rows = []
    for t in all_times_ordered:
        time_str = t.strftime('%H:%M')
        cells = []
        for i, dte in enumerate(day_list):
            ws = dte.weekday()
            if days[i]['ferme'] or t not in allowed_per_col[i]:
                cells.append(None)
                continue
            slot_dt = _instant_creneau(dte, t)
            if slot_dt <= now:
                cells.append(None)
                continue
            taken = Rendez_vous.objects.filter(date=slot_dt).exclude(status='cancelled').exists()
            cells.append({'value': slot_dt.isoformat(), 'available': not taken})
        h, m = t.hour, t.minute
        time_display = time_str + ' (après-midi)' if (h, m) >= (14, 0) else time_str
        rows.append({'time': time_str, 'time_display': time_display, 'cells': cells})
    return {'days': days, 'rows': rows}


def get_creneaux_disponibles_par_semaine():
    flat = get_creneaux_disponibles()
    from collections import OrderedDict

    by_week = OrderedDict()
    for value, label in flat:
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            dte = timezone.localtime(dt).date()
        except Exception:
            dte = None
        key = (dte - timedelta(days=dte.weekday())).isoformat() if dte else ''
        if key not in by_week:
            by_week[key] = []
        by_week[key].append((value, label))
    choices = [('', '--------- Choisir un créneau (date + heure) ---------')]
    for week_start_iso, slots in by_week.items():
        if not week_start_iso:
            choices.extend(slots)
            continue
        week_start = datetime.strptime(week_start_iso, '%Y-%m-%d').date()
        choices.append((f"Semaine du {week_start:%d/%m/%Y}", slots))
    return choices


def get_creneaux_for_date(dte, exclude_rdv_pk=None):
    if isinstance(dte, str):
        dte = datetime.strptime(dte, '%Y-%m-%d').date()
    now = _maintenant_utc()
    today_cabinet = timezone.localtime(now, _TZ_CABINET).date()
    if dte < today_cabinet:
        return []
    if JourFermeture.objects.filter(date=dte).exists():
        return []
    out = []
    for t in heures_pour_jour_semaine(dte.weekday()):
        slot_dt = _instant_creneau(dte, t)
        if slot_dt <= now:
            continue
        if not _rdv_occupe_slot(slot_dt, exclude_rdv_pk):
            out.append({'value': slot_dt.isoformat(), 'label': t.strftime('%H:%M')})
    return out


class RendezVousForm(forms.ModelForm):
    class Meta:
        model = Rendez_vous
        fields = ['titre', 'description', 'date', 'priority', 'service']
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Titre du rendez-vous'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Description (optionnel)'}),
            'service': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.exclude_rdv_pk = kwargs.pop('exclude_rdv_pk', None)
        super().__init__(*args, **kwargs)
        self.fields['service'].required = False
        self.fields['priority'].label = 'Type de cas'
        self.fields['priority'].widget.attrs['class'] = 'form-control'
        creneaux_flat = get_creneaux_disponibles(self.exclude_rdv_pk)
        self.fields['date'] = forms.CharField(
            required=True,
            label='Créneau (date et heure)',
            widget=forms.HiddenInput(attrs={'id': 'id_date'}),
        )
        if not creneaux_flat and not (self.instance and self.instance.pk):
            self.fields['date'].help_text = 'Aucun créneau disponible. Vérifiez les jours de fermeture.'

    def clean_date(self):
        date_val = self.cleaned_data.get('date')
        if not date_val:
            raise ValidationError('Veuillez choisir un créneau dans la liste.')
        try:
            dt = datetime.fromisoformat(date_val.replace('Z', '+00:00'))
        except Exception:
            raise ValidationError('Créneau invalide.')
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        if not est_creneau_horaire_officiel(dt):
            raise ValidationError('Cet horaire n’est pas un créneau autorisé.')
        if JourFermeture.objects.filter(date=timezone.localtime(dt).date()).exists():
            raise ValidationError('Ce jour est fermé.')
        if dt <= _maintenant_utc():
            raise ValidationError('Impossible de réserver un créneau déjà passé.')
        qs = Rendez_vous.objects.filter(date=dt).exclude(status='cancelled')
        if self.exclude_rdv_pk:
            qs = qs.exclude(pk=self.exclude_rdv_pk)
        if qs.exists():
            raise ValidationError('Ce créneau n’est plus disponible.')
        return dt
