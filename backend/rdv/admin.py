from django.contrib import admin
from django.contrib.admin import AdminSite
from django.template.response import TemplateResponse
from django.utils.html import format_html
from datetime import date

from .models import (
    Rendez_vous,
    Patient,
    Compte,
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

class CentreDentaireAdminSite(AdminSite):
    site_header = "Centre Dentaire"
    site_title  = "Administration"
    index_title = "Tableau de bord"
    site_url    = "/extranet/"

    def index(self, request, extra_context=None):
        context = {
            **self.each_context(request),
            "title"          : self.index_title,
            "app_list"       : self.get_app_list(request),
            "stats"          : self._get_dashboard_stats(),
            "rdv_aujourdhui" : self._get_rdv_aujourdhui(),
            "file_attente"   : self._get_file_attente(),
            "rdv_recents"    : self._get_rdv_recents(),
        }
        context.update(extra_context or {})
        return TemplateResponse(request, "admin/index.html", context)

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

    def _get_rdv_aujourdhui(self):
        today = date.today()
        return (
            Rendez_vous.objects
            .filter(date__date=today)
            .select_related("utilisateur", "service")
            .order_by("date")[:10]
        )

    def _get_file_attente(self):
        return (
            FileAttente.objects
            .select_related("rendez_vous", "rendez_vous__utilisateur")
            .order_by("numero_ticket")[:10]
        )

    def _get_rdv_recents(self):
        return (
            Rendez_vous.objects
            .select_related("utilisateur", "service")
            .order_by("-created_at")[:8]
        )


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

ROLE_CFG = {
    "admin": ("#7c3aed", "#ede9fe", "Admin"),
    "agent": ("#059669", "#d1fae5", "Agent"),
    "user" : ("#2563eb", "#dbeafe", "Patient"),
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
    c = ROLE_CFG.get(val)
    return _badge(*c) if c else val

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

class RendezVousAdmin(admin.ModelAdmin):
    list_display   = ("titre", "patient_nom", "service", "date", "statut_badge", "priorite_badge", "created_at")
    list_filter    = ("status", "priority", "service")
    search_fields  = ("titre", "utilisateur__username", "utilisateur__first_name", "utilisateur__last_name", "description")
    ordering       = ("-date",)
    date_hierarchy = "date"
    actions        = [action_confirmer, action_terminer, action_annuler, action_urgent, action_normal]
    list_per_page  = 25
    readonly_fields = ("created_at",)

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
    list_display    = ("nom", "user", "reference_courte", "nb_rdv")
    search_fields   = ("nom", "user__username", "user__email")
    ordering        = ("nom",)
    readonly_fields = ("reference",)
    list_per_page   = 25

    def reference_courte(self, obj):
        return str(obj.reference)[:8] + "..."
    reference_courte.short_description = "Reference"

    def nb_rdv(self, obj):
        return Rendez_vous.objects.filter(utilisateur=obj.user).count()
    nb_rdv.short_description = "Nb RDV"


# ══════════════════════════════════════════════
#  COMPTE
# ══════════════════════════════════════════════

class CompteAdmin(admin.ModelAdmin):
    list_display  = ("patient", "solde")
    search_fields = ("patient__nom",)
    ordering      = ("patient__nom",)


# ══════════════════════════════════════════════
#  UTILISATEUR
# ══════════════════════════════════════════════

class UtilisateurAdmin(admin.ModelAdmin):
    list_display  = ("user", "nom", "role_badge")
    list_filter   = ("role",)
    search_fields = ("nom", "user__username", "user__email")
    ordering      = ("nom",)

    def role_badge(self, obj):
        return badge_role(obj.role)
    role_badge.short_description = "Role"


# ══════════════════════════════════════════════
#  FILE ATTENTE
# ══════════════════════════════════════════════

class FileAttenteAdmin(admin.ModelAdmin):
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

class ServiceAdmin(admin.ModelAdmin):
    list_display  = ("nom", "duree_minutes", "description_courte")
    search_fields = ("nom",)
    ordering      = ("nom",)

    def description_courte(self, obj):
        return obj.description[:60] + "..." if len(obj.description) > 60 else obj.description
    description_courte.short_description = "Description"


# ══════════════════════════════════════════════
#  CRENEAU HORAIRE
# ══════════════════════════════════════════════

class CreneauHoraireAdmin(admin.ModelAdmin):
    list_display = ("jour_label", "heure_debut", "heure_fin", "actif")
    list_filter  = ("actif", "jour")
    ordering     = ("jour", "heure_debut")

    def jour_label(self, obj):
        return obj.get_jour_display()
    jour_label.short_description = "Jour"


# ══════════════════════════════════════════════
#  HORAIRE CABINET
# ══════════════════════════════════════════════

class HoraireCabinetAdmin(admin.ModelAdmin):
    list_display = ("jour_label", "heure_ouverture", "heure_fermeture", "actif")
    list_filter  = ("actif", "jour")
    ordering     = ("jour",)

    def jour_label(self, obj):
        return obj.get_jour_display()
    jour_label.short_description = "Jour"


# ══════════════════════════════════════════════
#  JOUR FERMETURE
# ══════════════════════════════════════════════

class JourFermetureAdmin(admin.ModelAdmin):
    list_display  = ("date", "motif")
    ordering      = ("date",)
    search_fields = ("motif",)


# ══════════════════════════════════════════════
#  CONVERSATION
# ══════════════════════════════════════════════

class ConversationAdmin(admin.ModelAdmin):
    list_display    = ("id", "utilisateur", "sujet", "statut_badge", "nombre_messages", "updated_at")
    list_filter     = ("statut",)
    search_fields   = ("utilisateur__username", "utilisateur__email", "sujet", "session_id")
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

class MessageChatbotAdmin(admin.ModelAdmin):
    list_display    = ("conversation", "role", "contenu_court", "intention_detectee", "confiance", "created_at")
    list_filter     = ("role",)
    search_fields   = ("contenu", "intention_detectee")
    ordering        = ("-created_at",)
    readonly_fields = ("created_at",)

    def contenu_court(self, obj):
        return obj.contenu[:80] + "..." if len(obj.contenu) > 80 else obj.contenu
    contenu_court.short_description = "Contenu"


# ══════════════════════════════════════════════
#  FAQ DENTAIRE
# ══════════════════════════════════════════════

class FAQDentaireAdmin(admin.ModelAdmin):
    list_display    = ("question_courte", "categorie", "priorite", "compteur_utilisation", "actif")
    list_filter     = ("categorie", "actif")
    search_fields   = ("question", "reponse", "mots_cles")
    ordering        = ("-priorite", "question")
    readonly_fields = ("compteur_utilisation", "date_creation")

    def question_courte(self, obj):
        return obj.question[:80] + "..." if len(obj.question) > 80 else obj.question
    question_courte.short_description = "Question"


# ══════════════════════════════════════════════
#  ACTION CHATBOT
# ══════════════════════════════════════════════

class ActionChatbotAdmin(admin.ModelAdmin):
    list_display    = ("nom", "type_action", "description_courte", "actif", "date_creation")
    list_filter     = ("actif", "type_action")
    search_fields   = ("nom", "description")
    readonly_fields = ("date_creation",)

    def description_courte(self, obj):
        return obj.description[:60] + "..." if len(obj.description) > 60 else obj.description
    description_courte.short_description = "Description"


# ══════════════════════════════════════════════
#  ENREGISTREMENT
# ══════════════════════════════════════════════

admin_site.register(Rendez_vous,    RendezVousAdmin)
admin_site.register(Patient,        PatientAdmin)
admin_site.register(Compte,         CompteAdmin)
admin_site.register(FileAttente,    FileAttenteAdmin)
admin_site.register(Utilisateur,    UtilisateurAdmin)
admin_site.register(Service,        ServiceAdmin)
admin_site.register(CreneauHoraire, CreneauHoraireAdmin)
admin_site.register(HoraireCabinet, HoraireCabinetAdmin)
admin_site.register(JourFermeture,  JourFermetureAdmin)
admin_site.register(Conversation,   ConversationAdmin)
admin_site.register(MessageChatbot, MessageChatbotAdmin)
admin_site.register(FAQDentaire,    FAQDentaireAdmin)
admin_site.register(ActionChatbot,  ActionChatbotAdmin)