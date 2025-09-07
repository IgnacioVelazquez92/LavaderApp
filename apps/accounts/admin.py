from django.contrib import admin
from .models import EmpresaMembership


@admin.register(EmpresaMembership)
class EmpresaMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "empresa", "rol")
    list_filter = ("rol",)
    search_fields = ("user__username", "user__email", "empresa__nombre")
