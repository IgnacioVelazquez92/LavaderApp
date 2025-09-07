# apps/accounts/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.shortcuts import redirect, render
from .forms.profile import ProfileForm
from .selectors import memberships_for


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"

    def get(self, request, *args, **kwargs):
        form = ProfileForm(instance=request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect("/cuenta/perfil/")
        return render(request, self.template_name, {"form": form})


class MembershipListView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/memberships.html"

    def get(self, request, *args, **kwargs):
        mems = memberships_for(request.user)
        return render(request, self.template_name, {"memberships": mems})
