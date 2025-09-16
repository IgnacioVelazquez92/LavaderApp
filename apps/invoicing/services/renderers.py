from __future__ import annotations

from typing import Optional

from django.template.loader import render_to_string

# Nota: para PDF en MVP podés usar WeasyPrint si está instalado.
try:
    from weasyprint import HTML  # type: ignore
    _PDF_AVAILABLE = True
except Exception:
    _PDF_AVAILABLE = False


def render_html(context: dict) -> str:
    """
    Renderiza el template imprimible a HTML crudo.
    Template esperado: 'invoicing/_invoice_print.html'
    """
    return render_to_string("invoicing/_invoice_print.html", context)


def html_to_pdf(html: str) -> Optional[bytes]:
    """
    Convierte HTML a PDF. Si no hay backend disponible, retorna None.
    MVP: opcional. Instalar 'weasyprint' para habilitar.
    """
    if not _PDF_AVAILABLE:
        return None
    pdf_bytes = HTML(string=html).write_pdf()
    return pdf_bytes
