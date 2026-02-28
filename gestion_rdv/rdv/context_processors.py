"""Context processor: nom d'affichage pour l'espace patient (pas l'email)."""


def user_display_name(request):
    """Ajoute user_display_name: prénom/nom ou partie avant @, jamais l'email brut."""
    out = {}
    if request.user.is_authenticated:
        nom = None
        try:
            nom = (getattr(request.user.patient_profile, 'nom', None) or '').strip() or nom
        except Exception:
            pass
        try:
            nom = (getattr(request.user.profile, 'nom', None) or '').strip() or nom
        except Exception:
            pass
        if not nom and (request.user.first_name or request.user.last_name):
            nom = (request.user.get_full_name() or '').strip() or None
        # Ne jamais afficher l'email ni la partie avant @ (ex. mahmour@gmail.com)
        out['user_display_name'] = nom or ''
    else:
        out['user_display_name'] = ''
    return out
