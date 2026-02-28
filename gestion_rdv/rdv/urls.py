from django.urls import path
from . import views

urlpatterns = [
    path('', views.accueil, name='accueil'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('agent/dashboard/', views.agent_dashboard, name='agent_dashboard'),
    path('agent/file-dattente/', views.agent_file_attente_view, name='agent_file_attente'),
    path('agent/rdv/<int:pk>/valider/', views.rdv_valider, name='rdv_valider'),
    path('agent/rdv/<int:pk>/annuler/', views.rdv_annuler, name='rdv_annuler'),
    path('agent/appeler-prochain/', views.agent_appeler_prochain, name='agent_appeler_prochain'),
    path('extranet/', views.extranet, name='extranet'),
    path('mes-rendez-vous/', views.rdv_list, name='rdv_list'),
    path('file-dattente/', views.file_attente_view, name='file_attente'),
    path('rdv/create/', views.rdv_create, name='rdv_create'),
    path('rdv/next/', views.rdv_next, name='rdv_next'),
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
]
