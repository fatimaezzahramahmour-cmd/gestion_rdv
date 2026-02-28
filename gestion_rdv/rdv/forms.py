from datetime import datetime, timedelta
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Rendez_vous, JourFermeture, HoraireCabinet

JOURS_NOMS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']


def get_creneaux_disponibles():
    """Liste de créneaux (value, label) : jours ouverts, horaires cabinet, pas déjà pris. Créneaux de 30 min."""
    now = timezone.now()
    start_date = now.date() if timezone.is_naive(now) else now.astimezone(timezone.get_current_timezone()).date()
    choices = []
    for d in range(28):
        dte = start_date + timedelta(days=d)
        if JourFermeture.objects.filter(date=dte).exists():
            continue
        jour_semaine = dte.weekday()
        horaires = HoraireCabinet.objects.filter(jour=jour_semaine, actif=True).order_by('heure_ouverture')
        for h in horaires:
            t = h.heure_ouverture
            while t < h.heure_fermeture:
                slot_naive = datetime.combine(dte, t)
                slot_dt = timezone.make_aware(slot_naive) if timezone.is_naive(slot_naive) else slot_naive
                if d == 0 and slot_dt <= now:
                    t = (datetime.combine(dte, t) + timedelta(minutes=30)).time()
                    continue
                if not Rendez_vous.objects.filter(date=slot_dt).exclude(status='cancelled').exists():
                    label = f"{JOURS_NOMS[jour_semaine]} {dte:%d/%m/%Y} à {t:%H:%M}"
                    value = slot_dt.isoformat()
                    choices.append((value, label))
                t = (datetime.combine(dte, t) + timedelta(minutes=30)).time()
    return choices[:200]


class RendezVousForm(forms.ModelForm):
    class Meta:
        model = Rendez_vous
        fields = ['titre', 'description', 'date', 'service']
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Titre du rendez-vous'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Description (optionnel)'}),
            'service': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['service'].required = False
        creneaux = get_creneaux_disponibles()
        self.fields['date'] = forms.ChoiceField(
            choices=[('', '--------- Choisir un créneau ---------')] + creneaux,
            label='Date et heure',
            widget=forms.Select(attrs={'class': 'form-control'}),
            required=True,
        )
        if not creneaux:
            self.fields['date'].help_text = 'Aucun créneau disponible. Vérifiez les horaires et jours de fermeture en admin.'

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
        return dt
