from django.contrib import admin
from django.contrib.admin import AdminSite
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from datetime import date

from .forms import UtilisateurAddForm
from .models import (
    Rendez_vous,
    Patient,
    FileAttente,
    Utilisateur,
    Service,
    CreneauHoraire,
    HoraireCabinet,
    JourFermeture,
    Conversation,
    MessageChatbot,
    FAQDentaire,
    ActionChatbot,
)


# ══════════════════════════════════════════════
#  CUSTOM ADMIN SITE
# ══════════════════════════════════════════════

# Menu admin cabinet
_ADMIN_MODEL_ORDER = [
    "utilisateur",
    "rendez_vous",
    "service",
    "creneauhoraire",
    "horairecabinet",
    "jourfermeture",
    "faqdentaire",
]

# Libellés menu (utilisateur → Comptes, rendez_vous → File d'attente)
_ADMIN_MENU_LABELS = {
    "utilisateur": "Comptes",
    "rendez_vous": "File d'attente",
    "faqdentaire": "FAQ dentaire",
}

# Masqués du menu
_ADMIN_MENU_HIDDEN = frozenset({
    "patient",
    "fileattente",
    "compte",
    "conversation",
    "messagechatbot",
    "actionchatbot",
})


_ICON_EDIT = mark_safe(
    '<svg class="admin-action-svg" xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>'
    '<path d="m15 5 4 4"/></svg>'
)
_ICON_DELETE = mark_safe(
    '<svg class="admin-action-svg" xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M3 6h18"/>'
    '<path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
    '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'
    '<line x1="10" x2="10" y1="11" y2="17"/>'
    '<line x1="14" x2="14" y1="11" y2="17"/></svg>'
)


def _admin_row_actions_html(modeladmin, request, obj):
    """Boutons modifier / supprimer (même rendu sur toutes les listes admin)."""
    opts = obj._meta
    url_name = f"centredentaireadmin:{opts.app_label}_{opts.model_name}"
    can_change = modeladmin.has_change_permission(request, obj)
    can_delete = modeladmin.has_delete_permission(request, obj)
    if not can_change and not can_delete:
        return "—"
    edit_btn = ""
    delete_btn = ""
    if can_change:
        edit_btn = format_html(
            '<a href="{}" class="admin-icon-btn admin-icon-btn--edit" title="Modifier" '
            'aria-label="Modifier">{}</a>',
            reverse(f"{url_name}_change", args=[obj.pk]),
            _ICON_EDIT,
        )
    if can_delete:
        delete_btn = format_html(
            '<a href="{}" class="admin-icon-btn admin-icon-btn--delete" title="Supprimer" '
            'aria-label="Supprimer">{}</a>',
            reverse(f"{url_name}_delete", args=[obj.pk]),
            _ICON_DELETE,
        )
    return format_html('<div class="admin-row-actions">{}{}</div>', edit_btn, delete_btn)


class AdminActionsColumnMixin:
    """Colonne Actions avec icônes — toutes les sections admin."""

    actions = None  # pas de menu « Action » groupé (Appliquer)

    def changelist_view(self, request, extra_context=None):
        self._actions_request = request
        response = super().changelist_view(request, extra_context)
        # TemplateResponse rendu après le return : garder request jusqu'au rendu
        if hasattr(response, "add_post_render_callback"):
            def _clear_actions_request(_response=None):
                self._actions_request = None
            response.add_post_render_callback(_clear_actions_request)
        else:
            self._actions_request = None
        return response

    @admin.display(description="Actions")
    def actions_icons(self, obj):
        request = getattr(self, "_actions_request", None)
        if request is None:
            return "—"
        return _admin_row_actions_html(self, request, obj)


class LectureSeuleAdminMixin:
    """Consultation uniquement — pas de création ni modification."""

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CentreDentaireAdminSite(AdminSite):
    site_header = "Centre Dentaire"
    site_title  = "Administration"
    index_title = ""
    site_url    = "/extranet/"

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label=app_label)
        order_index = {name: i for i, name in enumerate(_ADMIN_MODEL_ORDER)}

        def sort_key(model_entry):
            name = model_entry.get("object_name", "").lower()
            return (order_index.get(name, 999), model_entry.get("name", ""))

        for app in app_list:
            visible = []
            for m in app["models"]:
                key = m.get("object_name", "").lower()
                if key in _ADMIN_MENU_HIDDEN:
                    continue
                if key in _ADMIN_MENU_LABELS:
                    m = {**m, "name": _ADMIN_MENU_LABELS[key]}
                visible.append(m)
            app["models"] = sorted(visible, key=sort_key)
        return app_list

    def index(self, request, extra_context=None):
        context = {
            **self.each_context(request),
            "title"          : self.index_title,
            "app_list"       : self.get_app_list(request),
            "stats"          : self._get_dashboard_stats(),
            "rdv_en_attente" : self._get_rdv_par_statut("pending"),
            "rdv_appeles"    : self._get_rdv_par_statut("confirmed"),
            "rdv_termines"   : self._get_rdv_par_statut("done"),
        }
        context.update(extra_context or {})
        return TemplateResponse(request, "admin/index.html", context)

    def _get_rdv_par_statut(self, status, limit=12):
        from django.db.models import Case, When, IntegerField
        prio = Case(
            When(priority='urgent', then=0),
            When(priority='control', then=1),
            default=2,
            output_field=IntegerField(),
        )
        return (
            Rendez_vous.objects
            .filter(status=status)
            .select_related("utilisateur", "service")
            .order_by(prio, "date", "created_at")[:limit]
        )

    def _get_dashboard_stats(self):
        today = date.today()
        return {
            "total_patients" : Patient.objects.count(),
            "rdv_aujourdhui" : Rendez_vous.objects.filter(date__date=today).count(),
            "rdv_en_attente" : Rendez_vous.objects.filter(status="pending").count(),
            "rdv_confirmes"  : Rendez_vous.objects.filter(status="confirmed").count(),
            "rdv_termines"   : Rendez_vous.objects.filter(status="done").count(),
            "rdv_annules"    : Rendez_vous.objects.filter(status="cancelled").count(),
        }


admin_site = CentreDentaireAdminSite(name="centredentaireadmin")


# ══════════════════════════════════════════════
#  BADGES HTML
# ══════════════════════════════════════════════

STATUS_CFG = {
    "pending"  : ("#d97706", "#fef3c7", "En attente"),
    "confirmed": ("#059669", "#d1fae5", "Confirme"),
    "done"     : ("#6366f1", "#ede9fe", "Termine"),
    "cancelled": ("#dc2626", "#fee2e2", "Annule"),
}

PRIORITY_CFG = {
    "urgent" : ("#dc2626", "#fee2e2", "Urgent"),
    "normal" : ("#059669", "#d1fae5", "Normal"),
    "control": ("#2563eb", "#dbeafe", "Controle"),
}

ROLE_LABELS = {
    "admin": "Administrateur",
    "agent": "Réception",
    "user": "Patient",
}

STATUT_CONV_CFG = {
    "active"    : ("#059669", "#d1fae5", "Active"),
    "fermee"    : ("#6b7280", "#f3f4f6", "Fermee"),
    "transferee": ("#d97706", "#fef3c7", "Transferee"),
}


def _badge(color, bg, label):
    return format_html(
        '<span style="background:{bg};color:{color};border:1px solid {color}55;'
        'border-radius:20px;padding:2px 10px;font-size:11px;font-weight:700;">'
        '{label}</span>',
        bg=bg, color=color, label=label,
    )

def badge_status(val):
    c = STATUS_CFG.get(val)
    return _badge(*c) if c else val

def badge_priority(val):
    c = PRIORITY_CFG.get(val)
    return _badge(*c) if c else val

def badge_role(val):
    label = ROLE_LABELS.get(val, val)
    css_class = {
        "user": "role-badge role-badge--patient",
        "agent": "role-badge role-badge--agent",
        "admin": "role-badge role-badge--admin",
    }.get(val, "role-badge")
    return format_html('<span class="{}">{}</span>', css_class, label)

def badge_statut_conv(val):
    c = STATUT_CONV_CFG.get(val)
    return _badge(*c) if c else val


# ══════════════════════════════════════════════
#  ACTIONS GROUPEES
# ══════════════════════════════════════════════

@admin.action(description="Marquer comme confirme")
def action_confirmer(modeladmin, request, queryset):
    queryset.update(status="confirmed")

@admin.action(description="Marquer comme termine")
def action_terminer(modeladmin, request, queryset):
    queryset.update(status="done")

@admin.action(description="Marquer comme annule")
def action_annuler(modeladmin, request, queryset):
    queryset.update(status="cancelled")

@admin.action(description="Priorite : Urgent")
def action_urgent(modeladmin, request, queryset):
    queryset.update(priority="urgent")

@admin.action(description="Priorite : Normal")
def action_normal(modeladmin, request, queryset):
    queryset.update(priority="normal")


# ══════════════════════════════════════════════
#  RENDEZ_VOUS
# ══════════════════════════════════════════════

_FILE_ATTENTE_STATUS_FILTERS = (
    ("", "Tous"),
    ("pending", "En attente"),
    ("confirmed", "Appelés"),
    ("done", "Terminés"),
    ("cancelled", "Annulés"),
)

_COMPTE_ROLE_FILTERS = (
    ("", "Tous les rôles"),
    ("agent", "Réception"),
    ("user", "Patient"),
)

_ACTIF_FILTERS = (
    ("", "Tous"),
    ("1", "Actifs"),
    ("0", "Inactifs"),
)


def _filter_dropdown_options(request, param_name, choices, querydict=None):
    """Options pour select de filtre (liste admin)."""
    q = querydict.copy() if querydict is not None else request.GET.copy()
    current = request.GET.get(param_name, "")
    options = []
    for value, label in choices:
        params = q.copy()
        if value:
            params[param_name] = value
        else:
            params.pop(param_name, None)
        query = params.urlencode()
        options.append({
            "label": label,
            "value": value,
            "href": request.path + (f"?{query}" if query else ""),
            "selected": current == value,
        })
    return options


class RendezVousAdmin(LectureSeuleAdminMixin, admin.ModelAdmin):
    """File d'attente : visualisation seule (réception gère les RDV)."""

    list_display   = ("patient_nom", "service", "date", "statut_badge", "priorite_badge", "titre")
    list_filter    = ()
    search_fields  = ()
    ordering       = ("-date", "-created_at")
    change_list_template = "admin/rdv/file_attente_change_list.html"
    actions        = []
    list_per_page  = 30

    def get_list_display_links(self, request, list_display):
        return None

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["title"] = "File d'attente — consultation"
        extra_context["admin_filter_dropdowns"] = [
            {
                "id": "file-attente-status",
                "label": "Statut",
                "options": _filter_dropdown_options(
                    request, "status__exact", _FILE_ATTENTE_STATUS_FILTERS,
                ),
            },
        ]
        return super().changelist_view(request, extra_context=extra_context)

    def patient_nom(self, obj):
        return obj.utilisateur.get_full_name() or obj.utilisateur.username
    patient_nom.short_description = "Patient"

    def statut_badge(self, obj):
        return badge_status(obj.status)
    statut_badge.short_description = "Statut"

    def priorite_badge(self, obj):
        return badge_priority(obj.priority)
    priorite_badge.short_description = "Priorite"

# ══════════════════════════════════════════════
#  PATIENT
# ══════════════════════════════════════════════

class PatientAdmin(admin.ModelAdmin):
    """Fiche patient : création via Utilisateur (rôle Patient)."""

    list_display    = ("nom_affiche", "email_patient", "reference_courte", "nb_rdv")
    search_fields   = ()
    ordering        = ("nom",)
    readonly_fields = ("reference", "user")
    list_per_page   = 25
    fields          = ("user", "nom", "reference")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Nom", ordering="nom")
    def nom_affiche(self, obj):
        nom = (obj.nom or "").strip()
        if nom:
            return nom
        return obj.user.get_full_name() or obj.user.username or "—"

    @admin.display(description="E-mail", ordering="user__email")
    def email_patient(self, obj):
        return obj.user.email or "—"

    @admin.display(description="Référence")
    def reference_courte(self, obj):
        ref = str(obj.reference)
        return f"{ref[:8]}…"

    @admin.display(description="Nb RDV")
    def nb_rdv(self, obj):
        return Rendez_vous.objects.filter(utilisateur=obj.user).count()


# ══════════════════════════════════════════════
#  UTILISATEUR (agents + patients créés par l'admin)
# ══════════════════════════════════════════════

class UtilisateurAdmin(AdminActionsColumnMixin, admin.ModelAdmin):
    """Comptes agent ou patient créés par l'admin (choix du rôle à la création)."""

    list_display  = ("user", "nom_affiche", "role_badge", "actions_icons")
    list_filter   = ()
    search_fields = ()
    ordering      = ("nom",)
    add_form      = UtilisateurAddForm

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_filter_dropdowns"] = [
            {
                "id": "filter-compte-role",
                "label": "Rôle",
                "options": _filter_dropdown_options(
                    request, "role__exact", _COMPTE_ROLE_FILTERS,
                ),
            },
        ]
        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(role="admin").select_related("user")

    @admin.display(description="Nom", ordering="nom")
    def nom_affiche(self, obj):
        return (obj.nom or "").strip() or obj.user.get_full_name() or "—"

    @admin.display(description="Rôle", ordering="role")
    def role_badge(self, obj):
        return badge_role(obj.role)

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            return UtilisateurAddForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ('email', 'password', 'nom', 'role')
        return ('user', 'nom', 'role')

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.role == 'admin':
            return ('user', 'role')
        if obj:
            return ('user',)
        return ()

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == 'role' and not request.user.is_superuser:
            kwargs['choices'] = [
                ('agent', 'Réception'),
                ('user', 'Patient'),
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change and isinstance(form, UtilisateurAddForm):
            user = obj.user
            if not user.pk:
                user.save()
            Utilisateur.objects.update_or_create(
                user=user,
                defaults={
                    'nom': (obj.nom or '').strip() or user.get_full_name() or user.username,
                    'role': obj.role,
                },
            )
            return
        super().save_model(request, obj, form, change)
        if change and obj.role == 'agent':
            obj.user.is_staff = False
            obj.user.is_superuser = False
            obj.user.save(update_fields=['is_staff', 'is_superuser'])


# ══════════════════════════════════════════════
#  FILE ATTENTE
# ══════════════════════════════════════════════

class FileAttenteAdmin(LectureSeuleAdminMixin, admin.ModelAdmin):
    list_display    = ("numero_ticket", "patient_nom", "priorite_badge", "date_creation")
    list_filter     = ("priorite",)
    ordering        = ("numero_ticket",)
    readonly_fields = ("date_creation",)
    list_per_page   = 25

    def patient_nom(self, obj):
        if obj.rendez_vous and obj.rendez_vous.utilisateur:
            u = obj.rendez_vous.utilisateur
            return u.get_full_name() or u.username
        return "-"
    patient_nom.short_description = "Patient"

    def priorite_badge(self, obj):
        return badge_priority(obj.priorite)
    priorite_badge.short_description = "Priorite"


# ══════════════════════════════════════════════
#  SERVICE
# ══════════════════════════════════════════════

class ServiceAdmin(AdminActionsColumnMixin, admin.ModelAdmin):
    list_display  = ("nom", "duree_minutes", "description_courte", "actions_icons")
    list_filter   = ()
    search_fields = ()
    ordering      = ("nom",)

    def description_courte(self, obj):
        return obj.description[:60] + "..." if len(obj.description) > 60 else obj.description
    description_courte.short_description = "Description"


# ══════════════════════════════════════════════
#  CRENEAU HORAIRE
# ══════════════════════════════════════════════

class CreneauHoraireAdmin(AdminActionsColumnMixin, admin.ModelAdmin):
    list_display = ("jour_label", "heure_debut", "heure_fin", "actif", "actions_icons")
    list_filter  = ()
    ordering     = ("jour", "heure_debut")

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_filter_dropdowns"] = [
            {
                "id": "filter-creneau-actif",
                "label": "État",
                "options": _filter_dropdown_options(
                    request, "actif__exact", _ACTIF_FILTERS,
                ),
            },
        ]
        return super().changelist_view(request, extra_context)

    def jour_label(self, obj):
        return obj.get_jour_display()
    jour_label.short_description = "Jour"


# ══════════════════════════════════════════════
#  HORAIRE CABINET
# ══════════════════════════════════════════════

class HoraireCabinetAdmin(AdminActionsColumnMixin, admin.ModelAdmin):
    list_display = ("jour_label", "heure_ouverture", "heure_fermeture", "actif", "actions_icons")
    list_filter  = ()
    ordering     = ("jour",)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_filter_dropdowns"] = [
            {
                "id": "filter-horaire-actif",
                "label": "État",
                "options": _filter_dropdown_options(
                    request, "actif__exact", _ACTIF_FILTERS,
                ),
            },
        ]
        return super().changelist_view(request, extra_context)

    def jour_label(self, obj):
        return obj.get_jour_display()
    jour_label.short_description = "Jour"


# ══════════════════════════════════════════════
#  JOUR FERMETURE
# ══════════════════════════════════════════════

class JourFermetureAdmin(AdminActionsColumnMixin, admin.ModelAdmin):
    list_display  = ("date", "motif", "actions_icons")
    ordering      = ("date",)
    search_fields = ()


# ══════════════════════════════════════════════
#  CONVERSATION
# ══════════════════════════════════════════════

class ConversationAdmin(AdminActionsColumnMixin, admin.ModelAdmin):
    list_display    = ("id", "utilisateur", "sujet", "statut_badge", "nombre_messages", "updated_at", "actions_icons")
    list_filter     = ("statut",)
    search_fields   = ()
    ordering        = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at", "session_id")

    def statut_badge(self, obj):
        return badge_statut_conv(obj.statut)
    statut_badge.short_description = "Statut"

    def nombre_messages(self, obj):
        return obj.nombre_messages
    nombre_messages.short_description = "Messages"


# ══════════════════════════════════════════════
#  MESSAGE CHATBOT
# ══════════════════════════════════════════════

class MessageChatbotAdmin(AdminActionsColumnMixin, admin.ModelAdmin):
    list_display    = ("conversation", "role", "contenu_court", "intention_detectee", "confiance", "created_at", "actions_icons")
    list_filter     = ("role",)
    search_fields   = ()
    ordering        = ("-created_at",)
    readonly_fields = ("created_at",)

    def contenu_court(self, obj):
        return obj.contenu[:80] + "..." if len(obj.contenu) > 80 else obj.contenu
    contenu_court.short_description = "Contenu"


# ══════════════════════════════════════════════
#  FAQ DENTAIRE
# ══════════════════════════════════════════════

class FAQDentaireAdmin(AdminActionsColumnMixin, admin.ModelAdmin):
    list_display    = ("question_courte", "categorie", "priorite", "compteur_utilisation", "actif", "actions_icons")
    list_filter     = ("categorie", "actif")
    search_fields   = ()
    ordering        = ("-priorite", "question")
    readonly_fields = ("compteur_utilisation", "date_creation")

    def question_courte(self, obj):
        return obj.question[:80] + "..." if len(obj.question) > 80 else obj.question
    question_courte.short_description = "Question"


# ══════════════════════════════════════════════
#  ACTION CHATBOT
# ══════════════════════════════════════════════

class ActionChatbotAdmin(AdminActionsColumnMixin, admin.ModelAdmin):
    list_display    = ("nom", "type_action", "description_courte", "actif", "date_creation", "actions_icons")
    list_filter     = ("actif", "type_action")
    search_fields   = ()
    readonly_fields = ("date_creation",)

    def description_courte(self, obj):
        return obj.description[:60] + "..." if len(obj.description) > 60 else obj.description
    description_courte.short_description = "Description"


# ══════════════════════════════════════════════
#  ENREGISTREMENT
# ══════════════════════════════════════════════

admin_site.register(Rendez_vous,    RendezVousAdmin)
admin_site.register(Utilisateur,    UtilisateurAdmin)
admin_site.register(Service,        ServiceAdmin)
admin_site.register(CreneauHoraire, CreneauHoraireAdmin)
admin_site.register(HoraireCabinet, HoraireCabinetAdmin)
admin_site.register(JourFermeture,  JourFermetureAdmin)
admin_site.register(Conversation,   ConversationAdmin)
admin_site.register(MessageChatbot, MessageChatbotAdmin)
admin_site.register(FAQDentaire,    FAQDentaireAdmin)
admin_site.register(ActionChatbot,  ActionChatbotAdmin)