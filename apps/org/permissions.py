# apps/org/permissions.py
from enum import Enum
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property

from apps.accounts.models import EmpresaMembership
from apps.org.models import Empresa


SAFE_VIEWNAMES = {
    "org:selector",
    "account_login", "account_logout",
    "account_signup",
    "account_reset_password", "account_reset_password_done",
    "account_reset_password_from_key", "account_reset_password_from_key_done",
    "account_change_password", "account_change_password_done",
}


class EmpresaContextMixin(LoginRequiredMixin):
    """
    Resuelve empresa_activa y membership para la empresa en sesión.

    - No provoca redirect loop: si la petición es a una SAFE_VIEW, NO redirige.
    - Expone .empresa_activa, .membership, .is_admin, .is_owner para uso en vistas.
    """

    @cached_property
    def empresa_activa(self):
        empresa_id = self.request.session.get("empresa_id")
        if not empresa_id:
            return None
        try:
            # Solo empresas activas cuentan como contexto válido
            return Empresa.objects.get(pk=empresa_id, activo=True)
        except Empresa.DoesNotExist:
            return None

    @cached_property
    def membership(self):
        if not self.request.user.is_authenticated or not self.empresa_activa:
            return None
        # select_related para evitar N+1 en acceso a usuario/empresa
        return (
            EmpresaMembership.objects
            .select_related("user", "empresa", "sucursal_asignada")
            .filter(user=self.request.user, empresa=self.empresa_activa)
            .first()
        )

    @property
    def is_admin(self) -> bool:
        return bool(self.membership and self.membership.rol == EmpresaMembership.ROLE_ADMIN)

    @property
    def is_owner(self) -> bool:
        return bool(self.membership and getattr(self.membership, "is_owner", False))

    def _is_safe_view(self) -> bool:
        try:
            viewname = self.request.resolver_match.view_name  # más robusto que path
        except Exception:
            return False
        return viewname in SAFE_VIEWNAMES

    def _redirect_with_next(self, url_name: str):
        """
        Redirige preservando el destino original (?next=) para mejor UX.
        """
        target = reverse(url_name)
        # Solo agregamos next si es GET (evita colisiones con POST)
        if self.request.method == "GET":
            next_url = self.request.get_full_path()
            if next_url and next_url != target:
                return redirect(f"{target}?next={next_url}")
        return redirect(target)

    def _precheck_or_redirect(self):
        """
        Devuelve:
          - None si todo OK (seguir)
          - HttpResponseRedirect si hay que redirigir

        Reglas:
          - Superuser/staff pueden saltar controles (útil para soporte).
          - No redirige si ya estamos en una SAFE_VIEW (evita loops).
        """
        # Bypass de soporte (opcional pero útil)
        if self.request.user.is_authenticated and (
            self.request.user.is_superuser or self.request.user.is_staff
        ):
            return None

        # Si ya estamos en una vista segura, no intervenimos
        if self._is_safe_view():
            return None

        # Sin empresa activa → ir al selector
        if not self.empresa_activa:
            messages.error(self.request, "No tenés una empresa activa.")
            return self._redirect_with_next("org:selector")

        # Sin membership en esa empresa → limpiar sesión y selector
        if not self.membership:
            self.request.session.pop("empresa_id", None)
            self.request.session.pop("sucursal_id", None)
            messages.error(self.request, "No tenés acceso a esta empresa.")
            return self._redirect_with_next("org:selector")

        # Membership inactiva → bloquear (al home con mensaje)
        if not self.membership.activo:
            messages.error(
                self.request, "Tu acceso a esta empresa está deshabilitado.")
            return self._redirect_with_next("home")

        return None


class EmpresaMemberRequiredMixin(EmpresaContextMixin):
    """
    Requiere ser miembro ACTIVO de la empresa activa.
    No exige rol admin.
    """

    def dispatch(self, request, *args, **kwargs):
        redir = self._precheck_or_redirect()
        if redir:
            return redir
        return super().dispatch(request, *args, **kwargs)


class EmpresaAdminRequiredMixin(EmpresaContextMixin):
    """
    Requiere ser ADMIN ACTIVO de la empresa activa.
    """

    def dispatch(self, request, *args, **kwargs):
        redir = self._precheck_or_redirect()
        if redir:
            return redir

        if not self.is_admin:
            messages.error(
                self.request, "Se requieren permisos de administrador.")
            return self._redirect_with_next("home")

        return super().dispatch(request, *args, **kwargs)


# === Permisos granulares por feature ===

class Perm(str, Enum):
    ORG_VIEW = "org.view"
    ORG_EMPRESAS_MANAGE = "org.empresas.manage"
    ORG_SUCURSALES_MANAGE = "org.sucursales.manage"
    ORG_EMPLEADOS_MANAGE = "org.empleados.manage"

    CATALOG_SERVICES_MANAGE = "catalog.services.manage"
    CATALOG_PRICES_MANAGE = "catalog.prices.manage"

    REPORTS_VIEW = "reports.view"

    # CUSTOMERS
    CUSTOMERS_VIEW = "CUSTOMERS_VIEW"
    CUSTOMERS_CREATE = "CUSTOMERS_CREATE"
    CUSTOMERS_EDIT = "CUSTOMERS_EDIT"
    CUSTOMERS_DEACTIVATE = "CUSTOMERS_DEACTIVATE"
    CUSTOMERS_DELETE = "CUSTOMERS_DELETE"

    # VEHICLES (nuevo)
    VEHICLES_VIEW = "VEHICLES_VIEW"
    VEHICLES_CREATE = "VEHICLES_CREATE"
    VEHICLES_EDIT = "VEHICLES_EDIT"
    VEHICLES_DEACTIVATE = "VEHICLES_DEACTIVATE"
    VEHICLES_DELETE = "VEHICLES_DELETE"

    # VEHICLE TYPES (nuevo)
    VEHICLE_TYPES_VIEW = "VEHICLE_TYPES_VIEW"
    VEHICLE_TYPES_CREATE = "VEHICLE_TYPES_CREATE"
    VEHICLE_TYPES_EDIT = "VEHICLE_TYPES_EDIT"
    VEHICLE_TYPES_DEACTIVATE = "VEHICLE_TYPES_DEACTIVATE"
    VEHICLE_TYPES_DELETE = "VEHICLE_TYPES_DELETE"

    # Catálogo de servicios
    CATALOG_VIEW = "CATALOG_VIEW"
    CATALOG_CREATE = "CATALOG_CREATE"
    CATALOG_EDIT = "CATALOG_EDIT"
    CATALOG_DEACTIVATE = "CATALOG_DEACTIVATE"
    CATALOG_ACTIVATE = "CATALOG_ACTIVATE"
    CATALOG_DELETE = "CATALOG_DELETE"
    # === PRICING ===
    PRICING_VIEW = "PRICING_VIEW"
    PRICING_CREATE = "PRICING_CREATE"
    PRICING_EDIT = "PRICING_EDIT"
    PRICING_DEACTIVATE = "PRICING_DEACTIVATE"
    PRICING_DELETE = "PRICING_DELETE"

    # === SALES (nuevo) ===
    SALES_VIEW = "SALES_VIEW"
    SALES_CREATE = "SALES_CREATE"
    SALES_EDIT = "SALES_EDIT"
    SALES_FINALIZE = "SALES_FINALIZE"        # finalizar trabajo (TERMINADO)
    SALES_CANCEL = "SALES_CANCEL"            # cancelar (CANCELADO)
    SALES_DELETE = "SALES_DELETE"            # eliminar venta (si existe)
    SALES_ITEM_ADD = "SALES_ITEM_ADD"        # agregar ítems/servicios
    SALES_ITEM_UPDATE_QTY = "SALES_ITEM_UPDATE_QTY"
    SALES_ITEM_REMOVE = "SALES_ITEM_REMOVE"
    PROMO_VIEW = "promo_view"
    PROMO_CREATE = "promo_create"
    PROMO_EDIT = "promo_edit"
    PROMO_DELETE = "promo_delete"

    SALES_DISCOUNT_ADD = "sales.discount_add"     # aplicar descuentos/promos
    SALES_DISCOUNT_REMOVE = "sales.discount_remove"  # quitar ajustes
    SALES_PROMO_MANAGE = "sales.promo_manage"
    SALES_PROMO_APPLY = "sales.promo_apply"

    # === PAYMENTS ===
    PAYMENTS_VIEW = "PAYMENTS_VIEW"           # ver pagos (detalle/listado)
    PAYMENTS_CREATE = "PAYMENTS_CREATE"       # registrar pago
    # editar pago (si se habilita en roadmap)
    PAYMENTS_EDIT = "PAYMENTS_EDIT"
    PAYMENTS_DELETE = "PAYMENTS_DELETE"       # eliminar/revertir pago
    PAYMENTS_CONFIG = "PAYMENTS_CONFIG"       # gestionar medios de pago

    # === INVOICING ===
    # ver listados/detalles de comprobantes
    INVOICING_VIEW = "INVOICING_VIEW"
    # emitir comprobantes (requiere venta pagada)
    INVOICING_EMIT = "INVOICING_EMIT"
    # anular/revocar comprobantes ya emitidos
    INVOICING_ANNUL = "INVOICING_ANNUL"
    INVOICING_DOWNLOAD = "INVOICING_DOWNLOAD"     # descargar PDF/HTML
    # usar vistas públicas (generalmente sin auth)
    INVOICING_PUBLIC_ACCESS = "INVOICING_PUBLIC_ACCESS"


# Matriz de permisos por rol (podés ajustarla sin tocar vistas)
ROLE_POLICY = {
    "admin": {
        Perm.ORG_VIEW,
        Perm.ORG_EMPRESAS_MANAGE,
        Perm.ORG_SUCURSALES_MANAGE,
        Perm.ORG_EMPLEADOS_MANAGE,
        Perm.CATALOG_SERVICES_MANAGE,
        Perm.CATALOG_PRICES_MANAGE,
        Perm.REPORTS_VIEW,

        # Customers
        Perm.CUSTOMERS_VIEW,
        Perm.CUSTOMERS_CREATE,
        Perm.CUSTOMERS_EDIT,
        Perm.CUSTOMERS_DEACTIVATE,
        Perm.CUSTOMERS_DELETE,

        # Vehicles
        Perm.VEHICLES_VIEW,
        Perm.VEHICLES_CREATE,
        Perm.VEHICLES_EDIT,
        Perm.VEHICLES_DEACTIVATE,
        Perm.VEHICLES_DELETE,

        # Vehicle Types
        Perm.VEHICLE_TYPES_VIEW,
        Perm.VEHICLE_TYPES_CREATE,
        Perm.VEHICLE_TYPES_EDIT,
        Perm.VEHICLE_TYPES_DEACTIVATE,
        Perm.VEHICLE_TYPES_DELETE,

        # Catalog (nuevo)
        Perm.CATALOG_VIEW,
        Perm.CATALOG_CREATE,
        Perm.CATALOG_EDIT,
        Perm.CATALOG_DEACTIVATE,
        Perm.CATALOG_ACTIVATE,
        Perm.CATALOG_DELETE,

        # === PRICING (nuevo) ===
        Perm.PRICING_VIEW,
        Perm.PRICING_CREATE,
        Perm.PRICING_EDIT,
        Perm.PRICING_DEACTIVATE,
        Perm.PRICING_DELETE,

        # SALES (admin todo)
        Perm.SALES_VIEW,
        Perm.SALES_CREATE,
        Perm.SALES_EDIT,
        Perm.SALES_FINALIZE,
        Perm.SALES_CANCEL,
        Perm.SALES_DELETE,
        Perm.SALES_ITEM_ADD,
        Perm.SALES_ITEM_UPDATE_QTY,
        Perm.SALES_ITEM_REMOVE,

        Perm.PROMO_VIEW,
        Perm.PROMO_CREATE,
        Perm.PROMO_EDIT,
        Perm.PROMO_DELETE,

        # NUEVOS: SOLO ADMIN
        Perm.SALES_DISCOUNT_ADD,
        Perm.SALES_DISCOUNT_REMOVE,
        Perm.SALES_PROMO_MANAGE,
        Perm.SALES_PROMO_APPLY,

        # === PAYMENTS (admin total) ===
        Perm.PAYMENTS_VIEW,
        Perm.PAYMENTS_CREATE,
        Perm.PAYMENTS_EDIT,
        Perm.PAYMENTS_DELETE,
        Perm.PAYMENTS_CONFIG,

        Perm.INVOICING_VIEW,
        Perm.INVOICING_EMIT,
        Perm.INVOICING_ANNUL,
        Perm.INVOICING_DOWNLOAD,
        Perm.INVOICING_PUBLIC_ACCESS,
    },

    # Operador: solo puede ver catálogo (no crear/editar/borrar).
    "operador": {
        Perm.ORG_VIEW,
        Perm.CATALOG_SERVICES_MANAGE,
        Perm.CATALOG_PRICES_MANAGE,
        Perm.REPORTS_VIEW,

        # Customers
        Perm.CUSTOMERS_VIEW,
        Perm.CUSTOMERS_CREATE,
        Perm.CUSTOMERS_EDIT,

        # Vehicles
        Perm.VEHICLES_VIEW,
        Perm.VEHICLES_CREATE,
        Perm.VEHICLES_EDIT,

        # Vehicle Types (solo ver)
        Perm.VEHICLE_TYPES_VIEW,

        # Catalog
        Perm.CATALOG_VIEW,
        # === PRICING  ===
        Perm.PRICING_VIEW,

        # SALES (operativa diaria, sin acciones destructivas)
        Perm.SALES_VIEW,
        Perm.SALES_CREATE,
        Perm.SALES_EDIT,
        Perm.SALES_FINALIZE,
        Perm.SALES_ITEM_ADD,
        Perm.SALES_ITEM_UPDATE_QTY,
        Perm.SALES_ITEM_REMOVE,
        Perm.PROMO_VIEW,
        Perm.SALES_PROMO_APPLY,
        # === PAYMENTS (operativa diaria) ===
        Perm.PAYMENTS_VIEW,
        Perm.PAYMENTS_CREATE,

        Perm.INVOICING_VIEW,
        Perm.INVOICING_EMIT,        # puede emitir comprobantes de ventas pagadas
        Perm.INVOICING_DOWNLOAD,    # puede descargar comprobantes emitidos

    },

    # Supervisor: perfil de solo consulta, también puede ver catálogo.
    "supervisor": {
        Perm.ORG_VIEW,
        Perm.CATALOG_SERVICES_MANAGE,
        Perm.CATALOG_PRICES_MANAGE,
        Perm.REPORTS_VIEW,

        # Catalog
        Perm.CATALOG_VIEW,
        Perm.INVOICING_VIEW,
        Perm.INVOICING_DOWNLOAD,
    },
}


def has_empresa_perm(user, empresa, perm: Perm) -> bool:
    if not user or not empresa:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    mem = (
        EmpresaMembership.objects
        .filter(user=user, empresa=empresa, activo=True)
        .only("rol", "activo")
        .first()
    )
    if not mem:
        return False
    allowed = ROLE_POLICY.get(mem.rol, set())
    return perm in allowed


class EmpresaPermRequiredMixin(EmpresaContextMixin):
    """
    Mixin para CBVs: la vista declara required_perms = (Perm.XXXX, ...)
    y acá se valida todo (contexto + permisos).
    """
    required_perms = tuple()  # Ej: (Perm.CATALOG_PRICES_MANAGE,)

    def dispatch(self, request, *args, **kwargs):
        redir = self._precheck_or_redirect()
        if redir:
            return redir

        emp = self.empresa_activa
        for perm in self.required_perms:
            if not has_empresa_perm(request.user, emp, perm):
                messages.error(request, "No tenés permisos para esta acción.")
                return self._redirect_with_next("home")

        return super().dispatch(request, *args, **kwargs)
