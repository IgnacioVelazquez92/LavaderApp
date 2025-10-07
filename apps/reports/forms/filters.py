# apps/reports/forms/filters.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

# -------------------------------------------------------------------
# Este archivo define los FORMULARIOS DE FILTRO reutilizables para
# el módulo de reportería. Su responsabilidad es:
#   - Capturar parámetros de usuario de forma tipada y validarlos.
#   - Exponer un contrato JSON serializable (params) compatible
#     con SavedReport.params.
#   - Resolver dinámicamente choices (sucursal, métodos de pago,
#     estados de venta, turnos) respetando tenancy (empresa activa).
#
# Reglas:
#   - No contiene lógica de negocio ni consultas de agregación.
#   - No recalcula totales. Solo filtra/valida parámetros.
#   - No persiste nada. Los resultados se delegan a selectors/services.
# -------------------------------------------------------------------


# =========================
# Utilidades / Mixins
# =========================

class BootstrapFormMixin:
    """
    Inyecta clases Bootstrap a los widgets SIN usar .as_p hacks.
    """
    input_css = "form-control"
    select_css = "form-select"
    check_css = "form-check-input"

    def _apply_bootstrap(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.TextInput, forms.DateInput, forms.NumberInput)):
                widget.attrs.setdefault("class", self.input_css)
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", self.select_css)
            elif isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs.setdefault("class", self.check_css)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


@dataclass(frozen=True)
class DateRange:
    """DTO simple para representar un rango de fechas cerrado [desde, hasta]."""
    desde: date
    hasta: date

    def as_tuple(self) -> Tuple[date, date]:
        return (self.desde, self.hasta)


# =========================
# Helpers dinámicos de choices
# =========================

def _get_empresa(request) -> Optional[Any]:
    """
    Obtiene la empresa activa inyectada por TenancyMiddleware.
    En Admin u otros contextos puede no estar disponible.
    """
    return getattr(request, "empresa_activa", None)


def _sucursal_queryset_for(request) -> Any:
    """
    Retorna queryset de Sucursal limitado por empresa activa (si existe).
    Devuelve un queryset vacío si no se puede resolver el modelo.
    """
    empresa = _get_empresa(request)
    try:
        from apps.org.models import Sucursal
        qs = Sucursal.objects.all()
        if empresa is not None:
            qs = qs.filter(empresa=empresa)
        return qs
    except Exception:
        # Evita fallar duro si la importación aún no está disponible
        class _EmptyQS:
            def none(self): return self
        return _EmptyQS().none()


def _medio_pago_choices_for(request) -> List[Tuple[str, str]]:
    """
    Choices para métodos de pago activos de la empresa.
    Devuelve pares (str(id), nombre). Se usan como MultipleChoiceField.
    """
    empresa = _get_empresa(request)
    try:
        from apps.payments.models import MedioPago
        qs = MedioPago.objects.all()
        if empresa is not None:
            qs = qs.filter(empresa=empresa)
        qs = qs.filter(activo=True).order_by("nombre")
        return [(str(mp.pk), mp.nombre) for mp in qs]
    except Exception:
        return []


def _sales_status_choices() -> List[Tuple[str, str]]:
    """
    Choices para estados de la venta. Intenta importarlos desde Sales.
    Si no existen, provee un set mínimo común.
    """
    try:
        from apps.sales.models import SaleStatus  # Enum/TextChoices sugerido en tu app
        return list(SaleStatus.choices)
    except Exception:
        # Fallback genérico (no rompe contracto de params)
        return [
            ("borrador", _("Borrador")),
            ("en_proceso", _("En proceso")),
            ("terminado", _("Terminado")),
            # si tu UI trata 'payment_status' por separado, omítelo aquí
            ("pagado", _("Pagado")),
            ("cancelado", _("Cancelado")),
        ]


def _turno_queryset_for(request, sucursal: Optional[Any] = None,
                        dr: Optional[DateRange] = None) -> Any:
    """
    QS de TurnoCaja filtrado por empresa + sucursal + rango (opcional).
    Se usa para permitir filtrar reportes por un turno específico.
    """
    empresa = _get_empresa(request)
    try:
        from apps.cashbox.models import TurnoCaja
        qs = TurnoCaja.objects.all()
        if empresa is not None:
            qs = qs.filter(empresa=empresa)
        if sucursal is not None:
            qs = qs.filter(sucursal=sucursal)
        if dr is not None:
            # Turnos que intersectan el rango (apertura o cierre dentro)
            qs = qs.filter(abierto_en__date__gte=dr.desde,
                           abierto_en__date__lte=dr.hasta)
        return qs.order_by("-abierto_en")
    except Exception:
        class _EmptyQS:
            def none(self): return self
        return _EmptyQS().none()


# =========================
# Formulario principal de filtros
# =========================

class ReportFilterForm(BootstrapFormMixin, forms.Form):
    """
    Form de filtros estándar para la mayoría de reportes.

    Contrato de salida (params) — JSON serializable:
    {
      "fecha_desde": "YYYY-MM-DD",
      "fecha_hasta": "YYYY-MM-DD",
      "sucursal_id":  int | null,
      "metodos":      [int, ...],         # IDs de MedioPago
      "estados":      [str, ...],         # estados de venta
      "turno_id":     int | null,
      "granularidad": "dia"|"semana"|"mes"
    }

    Notas:
    - La granularidad sólo la usan reportes consolidados/analíticos.
    - 'metodos' y 'estados' son listas; el resto, escalares.
    - No se recalcula nada aquí: sólo validación de rango y consistencia básica.
    """

    # --- Configuración por defecto ---
    DEFAULT_RANGE_DAYS = 7         # Rango default (últimos N días)
    MAX_RANGE_DAYS = 93            # Rango máximo permitido (defensa API/UI)

    # --- Campos ---
    fecha_desde = forms.DateField(
        label=_("Desde"),
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Fecha inicial (incluida)."),
    )
    fecha_hasta = forms.DateField(
        label=_("Hasta"),
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Fecha final (incluida)."),
    )

    sucursal = forms.ModelChoiceField(
        label=_("Sucursal"),
        required=False,
        queryset=None,  # Se resuelve dinámicamente según empresa
        help_text=_("Limitar por sucursal (opcional)."),
    )

    metodos = forms.MultipleChoiceField(
        label=_("Métodos de pago"),
        required=False,
        choices=(),  # dinámico
        help_text=_("Uno o más métodos de pago (opcional)."),
        widget=forms.SelectMultiple(attrs={"data-allow-clear": "true"}),
    )

    estados = forms.MultipleChoiceField(
        label=_("Estados de venta"),
        required=False,
        choices=_sales_status_choices(),
        help_text=_("Estados de la venta para filtrar (opcional)."),
        widget=forms.SelectMultiple(attrs={"data-allow-clear": "true"}),
    )

    turno = forms.ModelChoiceField(
        label=_("Turno de caja"),
        required=False,
        queryset=None,  # dinámico con empresa/sucursal/fechas
        help_text=_("Filtrar por un turno específico (opcional)."),
    )

    GRANULARIDAD_CHOICES = (
        ("dia", _("Día")),
        ("semana", _("Semana")),
        ("mes", _("Mes")),
    )
    granularidad = forms.ChoiceField(
        label=_("Granularidad"),
        required=False,
        choices=GRANULARIDAD_CHOICES,
        help_text=_("Solo para reportes consolidados/analíticos."),
    )

    # --- Ciclo de vida del form ---

    def __init__(self, *args, **kwargs):
        """
        Este form espera opcionalmente:
          - request: para resolver empresa activa y limitar choices.
          - initial: si no se proveen fechas, asume últimos DEFAULT_RANGE_DAYS.
        """
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # Defaults inteligentes de fechas si no vinieron
        if not self.data and not self.initial:
            hoy = timezone.localdate()
            self.initial = {
                "fecha_desde": hoy - timedelta(days=self.DEFAULT_RANGE_DAYS - 1),
                "fecha_hasta": hoy,
            }

        # Resolve queryset dinámicos
        self.fields["sucursal"].queryset = _sucursal_queryset_for(self.request)
        self.fields["metodos"].choices = _medio_pago_choices_for(self.request)

        # Para el queryset de turno, necesitamos el rango inicial estimado:
        # (si hay data, se valida luego; si no, usamos initial)
        dr = self._build_initial_daterange()
        suc = None
        if "sucursal" in self.initial:
            suc = self.initial.get("sucursal")
        self.fields["turno"].queryset = _turno_queryset_for(
            self.request, sucursal=suc, dr=dr)

    # --- Helpers internos ---

    def _build_initial_daterange(self) -> DateRange:
        """
        Construye un DateRange usando data o initial (sin validar aún).
        Se usa sólo para precargar el queryset de turnos.
        """
        def _coerce_to_date(v, fallback: date) -> date:
            if isinstance(v, date):
                return v
            try:
                # Si viene como 'YYYY-MM-DD'
                return date.fromisoformat(str(v))
            except Exception:
                return fallback

        hoy = timezone.localdate()
        default_desde = hoy - timedelta(days=self.DEFAULT_RANGE_DAYS - 1)
        d = self.data or self.initial or {}
        desde = _coerce_to_date(d.get("fecha_desde"), default_desde)
        hasta = _coerce_to_date(d.get("fecha_hasta"), hoy)
        return DateRange(desde=desde, hasta=hasta)

    # --- Validaciones ---

    def clean(self):
        cleaned = super().clean()

        fdesde: date = cleaned.get("fecha_desde")
        fhasta: date = cleaned.get("fecha_hasta")

        if fdesde and fhasta:
            if fdesde > fhasta:
                raise ValidationError(
                    _("La fecha 'Desde' no puede ser posterior a 'Hasta'."))

            delta = (fhasta - fdesde).days + 1
            if delta > self.MAX_RANGE_DAYS:
                raise ValidationError(
                    _("El rango de fechas no puede exceder de %(n)d días."),
                    params={"n": self.MAX_RANGE_DAYS},
                )

        # Si vino turno, puede inferirse sucursal/fechas (opcional).
        turno = cleaned.get("turno")
        if turno:
            # si el usuario no eligió sucursal, la derivamos del turno
            if not cleaned.get("sucursal") and hasattr(turno, "sucursal"):
                cleaned["sucursal"] = turno.sucursal
            # el rango de fechas puede refinarse a la fecha del turno (opcional):
            # No forzamos para no sorpresivamente acotar el rango elegido.

        return cleaned

    # =========================
    # API del form → contrato params
    # =========================

    def to_params(self) -> Dict[str, Any]:
        """
        Serializa el form limpio a un dict listo para SavedReport.params.
        """
        if not self.is_valid():
            raise ValidationError(_("El formulario de filtros no es válido."))

        cd = self.cleaned_data
        # Normalizaciones:
        metodos_ids = [int(x) for x in cd.get(
            "metodos", []) if str(x).strip() != ""]
        estados = [str(x)
                   for x in cd.get("estados", []) if str(x).strip() != ""]
        sucursal_id = cd["sucursal"].pk if cd.get("sucursal") else None
        turno_id = cd["turno"].pk if cd.get("turno") else None
        gran = cd.get("granularidad") or None

        return {
            "fecha_desde": cd["fecha_desde"].isoformat(),
            "fecha_hasta": cd["fecha_hasta"].isoformat(),
            "sucursal_id": sucursal_id,
            "metodos": metodos_ids,
            "estados": estados,
            "turno_id": turno_id,
            "granularidad": gran,
        }

    # Conveniencia para cargar initial a partir de params
    @classmethod
    def initial_from_params(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convierte un dict de params (SavedReport.params) a 'initial' del form.
        Acepta strings ISO para fechas y listas para metodos/estados.
        """
        def _parse_date(s: Any, fallback: date) -> date:
            try:
                return date.fromisoformat(str(s))
            except Exception:
                return fallback

        hoy = timezone.localdate()
        default_desde = hoy - timedelta(days=cls.DEFAULT_RANGE_DAYS - 1)
        return {
            "fecha_desde": _parse_date(params.get("fecha_desde"), default_desde),
            "fecha_hasta": _parse_date(params.get("fecha_hasta"), hoy),
            "sucursal": params.get("sucursal_id"),
            "metodos": params.get("metodos", []),
            "estados": params.get("estados", []),
            "turno": params.get("turno_id"),
            "granularidad": params.get("granularidad"),
        }

    # =========================
    # Accesorios útiles para selectors/services
    # =========================

    def date_range(self) -> DateRange:
        """Devuelve el rango de fechas validado como DateRange."""
        if not self.is_valid():
            raise ValidationError(_("El formulario de filtros no es válido."))
        return DateRange(self.cleaned_data["fecha_desde"], self.cleaned_data["fecha_hasta"])

    def selected_sucursal(self) -> Optional[Any]:
        """Sucursal ya cargada (o None)."""
        if not self.is_valid():
            raise ValidationError(_("El formulario de filtros no es válido."))
        return self.cleaned_data.get("sucursal")

    def selected_metodos_ids(self) -> List[int]:
        """IDs (int) de medios de pago elegidos (puede ser lista vacía)."""
        if not self.is_valid():
            raise ValidationError(_("El formulario de filtros no es válido."))
        return [int(x) for x in self.cleaned_data.get("metodos", []) if str(x).strip() != ""]

    def selected_estados(self) -> List[str]:
        """Estados de venta elegidos (puede ser lista vacía)."""
        if not self.is_valid():
            raise ValidationError(_("El formulario de filtros no es válido."))
        return [str(x) for x in self.cleaned_data.get("estados", []) if str(x).strip() != ""]

    def selected_turno(self) -> Optional[Any]:
        """TurnoCaja seleccionado (o None)."""
        if not self.is_valid():
            raise ValidationError(_("El formulario de filtros no es válido."))
        return self.cleaned_data.get("turno")

    def selected_granularidad(self) -> Optional[str]:
        """Granularidad elegida (o None)."""
        if not self.is_valid():
            raise ValidationError(_("El formulario de filtros no es válido."))
        return self.cleaned_data.get("granularidad") or None
