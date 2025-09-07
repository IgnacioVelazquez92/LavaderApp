# apps/accounts/urls.py
from django.urls import path, include
from .views import ProfileView, MembershipListView

urlpatterns = [
    path("cuenta/perfil/", ProfileView.as_view(), name="accounts_profile"),
    path("cuenta/membresias/", MembershipListView.as_view(),
         name="accounts_memberships"),
]
