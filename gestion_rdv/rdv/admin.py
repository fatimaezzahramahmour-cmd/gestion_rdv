from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    Rendez_vous, Utilisateur, Service, CreneauHoraire,
    Patient, Compte, FileAttente, JourFermeture, HoraireCabinet
)


def make_confirmed(modeladmin, request, queryset):
	updated = queryset.update(status='confirmed')
	modeladmin.message_user(request, _('%d rendez-vous marqués comme "confirmed"') % updated)


def make_done(modeladmin, request, queryset):
	updated = queryset.update(status='done')
	modeladmin.message_user(request, _('%d rendez-vous marqués comme "done"') % updated)


def make_cancelled(modeladmin, request, queryset):
	updated = queryset.update(status='cancelled')
	modeladmin.message_user(request, _('%d rendez-vous marqués comme "cancelled"') % updated)


def set_priority_urgent(modeladmin, request, queryset):
	updated = queryset.update(priority='urgent')
	modeladmin.message_user(request, _('%d rendez-vous passés en priorité "urgent"') % updated)


def set_priority_normal(modeladmin, request, queryset):
	updated = queryset.update(priority='normal')
	modeladmin.message_user(request, _('%d rendez-vous passés en priorité "normal"') % updated)


def assign_to_me(modeladmin, request, queryset):
	updated = queryset.update(utilisateur=request.user)
	modeladmin.message_user(request, _('%d rendez-vous assignés à vous') % updated)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
	list_display = ('nom', 'duree_minutes', 'description', 'image_url')
	search_fields = ('nom',)


@admin.register(CreneauHoraire)
class CreneauHoraireAdmin(admin.ModelAdmin):
	list_display = ('jour', 'heure_debut', 'heure_fin', 'actif')
	list_display_links = ('jour', 'heure_debut', 'heure_fin')
	list_filter = ('jour', 'actif')
	list_editable = ('actif',)
	list_per_page = 25


@admin.register(Rendez_vous)
class RendezVousAdmin(admin.ModelAdmin):
	list_display = ('titre', 'utilisateur', 'service', 'date', 'status', 'priority', 'created_at')
	list_filter = ('date', 'utilisateur', 'status', 'priority', 'service')
	search_fields = ('titre', 'description', 'utilisateur__username')
	actions = [make_confirmed, make_done, make_cancelled, set_priority_urgent, set_priority_normal, assign_to_me]


@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
	list_display = ('user', 'nom', 'role')
	search_fields = ('user__username', 'nom', 'user__email')


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
	list_display = ('id', 'nom', 'user')
	search_fields = ('nom', 'user__username')


@admin.register(Compte)
class CompteAdmin(admin.ModelAdmin):
	list_display = ('patient', 'solde')
	search_fields = ('patient__nom',)


@admin.register(FileAttente)
class FileAttenteAdmin(admin.ModelAdmin):
	list_display = ('numero_ticket', 'priorite', 'rendez_vous', 'date_creation')
	list_filter = ('priorite',)


@admin.register(JourFermeture)
class JourFermetureAdmin(admin.ModelAdmin):
	list_display = ('date', 'motif')
	date_hierarchy = 'date'


@admin.register(HoraireCabinet)
class HoraireCabinetAdmin(admin.ModelAdmin):
	list_display = ('jour', 'heure_ouverture', 'heure_fermeture', 'actif')
	list_display_links = ('jour', 'heure_ouverture', 'heure_fermeture')
	list_filter = ('jour', 'actif')
	list_editable = ('actif',)
	list_per_page = 25
	fields = ('jour', 'heure_ouverture', 'heure_fermeture', 'actif')
# ============================================================================
# CHATBOT ADMIN
# ============================================================================

from .models import Conversation, MessageChatbot, FAQDentaire, ActionChatbot


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'utilisateur', 'session_id', 'sujet', 'statut', 'created_at']
    list_filter = ['statut', 'created_at']
    search_fields = ['session_id', 'sujet', 'utilisateur__email']


@admin.register(MessageChatbot)
class MessageChatbotAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'role', 'contenu', 'intention_detectee', 'created_at']
    list_filter = ['role', 'intention_detectee', 'created_at']


@admin.register(FAQDentaire)
class FAQDentaireAdmin(admin.ModelAdmin):
    list_display = ['question', 'categorie', 'actif', 'priorite', 'compteur_utilisation', 'date_creation']
    list_editable = ['actif', 'priorite']
    list_filter = ['categorie', 'actif', 'date_creation']
    search_fields = ['question', 'reponse']
    ordering = ['-priorite', 'question']
    readonly_fields = ['compteur_utilisation', 'date_creation']


@admin.register(ActionChatbot)
class ActionChatbotAdmin(admin.ModelAdmin):
    list_display = ['nom', 'type_action', 'actif']
    list_filter = ['type_action', 'actif']