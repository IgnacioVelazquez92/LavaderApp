from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.org.models import Empresa, Sucursal
from apps.cashbox.models import TurnoCaja, TurnoCajaTotal
from apps.cashbox.services.cashbox import (
    abrir_turno,
    cerrar_turno,
    TurnoAbiertoExistenteError,
    TurnoNoAbiertoError,
)

User = get_user_model()


class TurnoCajaModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.empresa = Empresa.objects.create(
            nombre="Empresa Test", subdominio="empresatest"
        )
        self.sucursal = Sucursal.objects.create(
            empresa=self.empresa, 
            nombre="Sucursal Central",
            codigo_interno="SUC001"
        )

    def test_turno_creation(self):
        turno = TurnoCaja.objects.create(
            empresa=self.empresa,
            sucursal=self.sucursal,
            abierto_por=self.user,
            responsable_nombre="Juan Perez",
        )
        self.assertEqual(turno.empresa, self.empresa)
        self.assertEqual(turno.sucursal, self.sucursal)
        self.assertTrue(turno.esta_abierto)
        self.assertIsNone(turno.cerrado_en)

    def test_turno_str(self):
        turno = TurnoCaja.objects.create(
            empresa=self.empresa,
            sucursal=self.sucursal,
            abierto_por=self.user,
        )
        self.assertIn("ABIERTO", str(turno))
        self.assertIn(self.sucursal.nombre, str(turno))

    def test_unique_turno_abierto_por_sucursal(self):
        TurnoCaja.objects.create(
            empresa=self.empresa,
            sucursal=self.sucursal,
            abierto_por=self.user,
        )
        with self.assertRaises(Exception):
            TurnoCaja.objects.create(
                empresa=self.empresa,
                sucursal=self.sucursal,
                abierto_por=self.user,
            )

    def test_turno_rango(self):
        turno = TurnoCaja.objects.create(
            empresa=self.empresa,
            sucursal=self.sucursal,
            abierto_por=self.user,
        )
        desde, hasta = turno.rango()
        self.assertEqual(desde, turno.abierto_en)
        self.assertIsNotNone(hasta)


class TurnoCajaServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.empresa = Empresa.objects.create(
            nombre="Empresa Test", subdominio="empresatest"
        )
        self.sucursal = Sucursal.objects.create(
            empresa=self.empresa, 
            nombre="Sucursal Central",
            codigo_interno="SUC001"
        )

    def test_abrir_turno_exitoso(self):
        turno = abrir_turno(
            empresa=self.empresa,
            sucursal=self.sucursal,
            user=self.user,
            responsable_nombre="Juan Perez",
        )
        self.assertIsNotNone(turno.id)
        self.assertTrue(turno.esta_abierto)
        self.assertEqual(turno.abierto_por, self.user)

    def test_abrir_turno_con_turno_existente(self):
        abrir_turno(
            empresa=self.empresa, sucursal=self.sucursal, user=self.user
        )
        with self.assertRaises(TurnoAbiertoExistenteError):
            abrir_turno(
                empresa=self.empresa, sucursal=self.sucursal, user=self.user
            )

    def test_cerrar_turno_exitoso(self):
        turno = abrir_turno(
            empresa=self.empresa, sucursal=self.sucursal, user=self.user
        )
        resultado = cerrar_turno(
            turno=turno,
            user=self.user,
            monto_contado_total=Decimal("100.00"),
            recalcular_y_guardar_totales=False,
        )
        self.assertIsNotNone(resultado.turno.cerrado_en)
        self.assertEqual(resultado.turno.cerrado_por, self.user)
        self.assertFalse(resultado.turno.esta_abierto)

    def test_cerrar_turno_ya_cerrado(self):
        turno = abrir_turno(
            empresa=self.empresa, sucursal=self.sucursal, user=self.user
        )
        cerrar_turno(turno=turno, user=self.user,
                     recalcular_y_guardar_totales=False)
        with self.assertRaises(TurnoNoAbiertoError):
            cerrar_turno(turno=turno, user=self.user,
                         recalcular_y_guardar_totales=False)
