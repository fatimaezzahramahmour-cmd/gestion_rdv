from django.urls import path, include
from rdv.admin import admin_site

urlpatterns = [
    path('admin/', admin_site.urls),
    path('', include('rdv.urls')),
]