from rest_framework.permissions import BasePermission
from django.core.exceptions import PermissionDenied

class EstPatient(BasePermission):
    """
    Autorise uniquement les patients (role='user')
    Utilisé pour protéger /extranet/ et /rdv/
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'utilisateur') and
            request.user.utilisateur.role == 'user'
        )

class EstAgent(BasePermission):
    """
    Autorise uniquement les agents (role='agent')
    Utilisé pour protéger /agent/dashboard/
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'utilisateur') and
            request.user.utilisateur.role == 'agent'
        )

class EstAdmin(BasePermission):
    """
    Autorise uniquement les admins (role='admin')
    Utilisé pour protéger /admin/dashboard/
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'utilisateur') and
            request.user.utilisateur.role == 'admin'
        )