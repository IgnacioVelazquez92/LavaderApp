# Documentación de Modelos — SaaS Lavaderos

Este documento consolida el **modelo de datos** y lo complementa con **reglas de negocio**, **procesos granulares con entradas/salidas**, **estados**, **restricciones** e **indicadores**. El objetivo es mantener un **MVP simple, vendible y operable**, evitando complejidades innecesarias pero dejando espacio para escalar.

---

## 0) Alcance y principios del MVP

- **Simplicidad primero**: cubrir recepción → venta → cobro → comprobante no fiscal → cierre de caja.
- **Multitenant real**: todo cuelga de `EMPRESA`. Datos aislados por empresa.
- **Precios determinísticos**: resolución por `sucursal + servicio + tipo_vehiculo + fecha`.
- **Trazabilidad**: cada venta tiene cliente, vehículo, ítems, pagos, comprobante y notificaciones.
- **Operable en campo**: flujos en 5–7 toques; mínimos obligatorios.
- **Medible**: ventas, ticket promedio, servicios top, métodos de pago, propinas.

### Mejoras sugeridas

1. **Índices y restricciones** (ver §5) para evitar inconsistencias y acelerar consultas.
2. **Estados explícitos de venta** (ver §3.1) y transiciones claras.
3. **Campos de tiempo de proceso** opcionales en `VENTA` (`iniciado_en`, `finalizado_en`) para medir lead time. _(Opcional, pero muy útil para tiempos y productividad)_
4. **Normalización mínima de patente y teléfono** para evitar duplicados por formato. _(sin crear nuevas tablas)_
5. **Plantillas de notificación** por empresa con **placeholders estándar** (`{{nombre}}`, `{{patente}}`, `{{total}}`).

---

## 1) Vista A — Organización y Clientes

```mermaid
erDiagram
  EMPRESA ||--o{ SUCURSAL : "tiene"
  EMPRESA ||--o{ USUARIO : "usuarios"
  EMPRESA ||--o{ CLIENTE : "clientes"
  EMPRESA ||--o{ TIPO_VEHICULO : "configura"
  EMPRESA ||--o{ EMPRESA_CONFIG : "config"
  CLIENTE ||--o{ VEHICULO : "posee"
  TIPO_VEHICULO ||--o{ VEHICULO : "clasifica"

  EMPRESA {
    uuid id PK
    string nombre
    string subdominio
    string logo_url
    string zona_horaria
    json extra_json
    datetime creado_en
    datetime actualizado_en
    datetime eliminado_en
    bool activo
  }
  EMPRESA_CONFIG {
    uuid id PK
    uuid empresa_id FK
    string clave
    json valor_json
    string scope
    datetime creado_en
  }
  SUCURSAL {
    uuid id PK
    uuid empresa_id FK
    string nombre
    string direccion
    string codigo_erp
    datetime creado_en
    datetime actualizado_en
    datetime eliminado_en
    bool activo
  }
  USUARIO {
    uuid id PK
    uuid empresa_id FK
    string email
    string nombre_completo
    string rol
    datetime creado_en
    datetime actualizado_en
    datetime eliminado_en
    bool activo
  }
  CLIENTE {
    uuid id PK
    uuid empresa_id FK
    string nombre
    string apellido
    string email
    string telefono_wpp
    date fecha_nac
    json extra_json
    datetime creado_en
    datetime actualizado_en
    datetime eliminado_en
    bool activo
  }
  TIPO_VEHICULO {
    uuid id PK
    uuid empresa_id FK
    string nombre
    bool activo
  }
  VEHICULO {
    uuid id PK
    uuid empresa_id FK
    uuid cliente_id FK
    uuid tipo_vehiculo_id FK
    string marca
    string modelo
    string patente
    json extra_json
    datetime creado_en
    datetime actualizado_en
    datetime eliminado_en
    bool activo
  }
```

**Notas y propósito**

- **EMPRESA**: tenant; raíz jerárquica.
- **EMPRESA_CONFIG**: extensión por claves (p.ej., `moneda`, `propina_porcentual_sugerida`, `habilitar_whatsapp`).
- **SUCURSAL**: soporta `codigo_erp` para mapear con sistemas existentes.
- **USUARIO**: autorización por rol simple (ver §6).
- **CLIENTE**: datos básicos y `extra_json` para campos libres.
- **TIPO_VEHICULO**: catálogo simple.
- **VEHICULO**: vehículo por cliente; `patente` utilizada para búsquedas rápidas.

---

## 2) Vista B — Catálogo y Precios

```mermaid
erDiagram
  EMPRESA ||--o{ SERVICIO : "define"
  SERVICIO ||--o{ PRECIO_SERVICIO : "tarifa"
  SUCURSAL ||--o{ PRECIO_SERVICIO : "usa"
  TIPO_VEHICULO ||--o{ PRECIO_SERVICIO : "aplica"

  SERVICIO {
    uuid id PK
    uuid empresa_id FK
    string nombre
    string descripcion
    bool activo
    datetime creado_en
    datetime actualizado_en
    datetime eliminado_en
  }
  PRECIO_SERVICIO {
    uuid id PK
    uuid empresa_id FK
    uuid sucursal_id FK
    uuid servicio_id FK
    uuid tipo_vehiculo_id FK
    decimal precio
    string moneda
    date vigencia_inicio
    date vigencia_fin
    bool activo
    datetime creado_en
  }
```

**Notas y propósito**

- **SERVICIO**: catálogo (lavado, encerado, interior, etc.).
- **PRECIO_SERVICIO**: tarifa efectiva por `sucursal + tipo_vehiculo + servicio + rango de vigencia`.

---

## 3) Vista C — Ventas, Pagos, Comprobantes y Cierre

```mermaid
erDiagram
  SUCURSAL ||--o{ VENTA : "registra"
  CLIENTE ||--o{ VENTA : "compra"
  VEHICULO ||--o{ VENTA : "para"
  VENTA ||--|{ VENTA_ITEM : "contiene"
  SERVICIO ||--o{ VENTA_ITEM : "se_vende"
  VENTA ||--o{ PAGO : "recibe"
  VENTA ||--o{ COMPROBANTE : "emite"
  VENTA ||--o{ LOG_NOTIF : "notifica"
  SUCURSAL ||--o{ SECUENCIA_COMPROBANTE : "numeracion"
  CLIENTE ||--o{ CLIENTE_FACTURACION : "datos_facturacion"
  SUCURSAL ||--o{ CIERRE_CAJA : "cierra"
  CIERRE_CAJA ||--o{ CIERRE_CAJA_TOTAL : "totales_por_metodo"

  VENTA {
    uuid id PK
    uuid empresa_id FK
    uuid sucursal_id FK
    uuid cliente_id FK
    uuid vehiculo_id FK
    datetime creado_en
    datetime actualizado_en
    string estado
    decimal subtotal
    decimal descuento
    decimal propina
    decimal total
    decimal saldo_pendiente
    string notas
  }
  VENTA_ITEM {
    uuid id PK
    uuid venta_id FK
    uuid servicio_id FK
    string servicio_nombre_cache
    decimal precio_unitario
    int cantidad
    decimal total_linea
  }
  PAGO {
    uuid id PK
    uuid venta_id FK
    string metodo
    decimal monto
    bool es_propina
    string referencia
    string idempotency_key
    datetime pagado_en
  }
  CLIENTE_FACTURACION {
    uuid id PK
    uuid cliente_id FK
    string razon_social
    string cuit
    string direccion
    string ciudad
    string provincia
    string codigo_postal
    bool activo
  }
  COMPROBANTE {
    uuid id PK
    uuid venta_id FK
    uuid cliente_facturacion_id FK
    string tipo
    string punto_venta
    string numero
    decimal total
    string moneda
    string pdf_url
    datetime emitido_en
  }
  SECUENCIA_COMPROBANTE {
    uuid id PK
    uuid sucursal_id FK
    string tipo
    int proximo_numero
    datetime actualizado_en
  }
  PLANTILLA_NOTIF {
    uuid id PK
    uuid empresa_id FK
    string clave
    string canal
    text cuerpo_tpl
    bool activo
  }
  LOG_NOTIF {
    uuid id PK
    uuid venta_id FK
    string canal
    string destinatario
    text cuerpo_renderizado
    string estado
    datetime enviado_en
  }
  CIERRE_CAJA {
    uuid id PK
    uuid empresa_id FK
    uuid sucursal_id FK
    uuid usuario_id FK
    datetime abierto_en
    datetime cerrado_en
    string notas
  }
  CIERRE_CAJA_TOTAL {
    uuid id PK
    uuid cierre_caja_id FK
    string metodo
    decimal monto
    decimal propinas
  }
```

**Reglas y fórmulas mínimas**

- `total_linea = cantidad * precio_unitario`
- `subtotal = SUM(total_linea)`
- `total = subtotal - descuento + propina`
- `saldo_pendiente = total - SUM(pagos donde es_propina=false)`
- La **propina** se almacena también en `PAGO.es_propina=true` si se cobra separada por método.

### 3.1) Estados de una venta (MVP)

```mermaid
stateDiagram-v2
  [*] --> borrador
  borrador --> en_proceso: agregar/editar items
  en_proceso --> terminado: trabajo finalizado
  terminado --> pagado: pagos = total
  en_proceso --> pagado: pago completo antes de terminar
  borrador --> cancelado: anulación
  en_proceso --> cancelado: anulación
  pagado --> [*]
  cancelado --> [*]
```

---

## 4) Vista D — SaaS y Observabilidad

```mermaid
erDiagram
  PLAN_SAAS ||--o{ SUSCRIPCION_SAAS : "asigna"
  EMPRESA ||--o{ SUSCRIPCION_SAAS : "suscribe"
  EMPRESA ||--o{ FACTURA_SAAS : "facturas_saas"
  FACTURA_SAAS ||--o{ PAGO_SAAS : "pagos"
  EMPRESA ||--o{ APP_LOG : "genera"
  EMPRESA ||--o{ AUDITORIA_CAMBIO : "audita"
  EMPRESA ||--o{ OUTBOX_EVENT : "eventos_tx"

  PLAN_SAAS {
    uuid id PK
    string nombre
    int max_sucursales
    int max_usuarios
    int max_storage_mb
    decimal precio_mensual
    bool activo
  }
  SUSCRIPCION_SAAS {
    uuid id PK
    uuid empresa_id FK
    uuid plan_saas_id FK
    string estado
    date inicio
    date fin
  }
  FACTURA_SAAS {
    uuid id PK
    uuid empresa_id FK
    date periodo
    decimal total
    string moneda
    string estado
    string pdf_url
    datetime emitido_en
  }
  PAGO_SAAS {
    uuid id PK
    uuid factura_saas_id FK
    string metodo
    decimal monto
    string referencia
    datetime pagado_en
  }
  APP_LOG {
    uuid id PK
    uuid empresa_id FK
    string nivel
    string origen
    string evento
    text mensaje
    text meta_json
    datetime creado_en
  }
  AUDITORIA_CAMBIO {
    uuid id PK
    uuid empresa_id FK
    uuid usuario_id FK
    string tabla
    string fila_pk
    string accion
    text diff_json
    datetime creado_en
  }
  OUTBOX_EVENT {
    uuid id PK
    uuid empresa_id FK
    string tipo
    text payload_json
    datetime creado_en
    datetime procesado_en
  }
```

**Eventos recomendados (Outbox, MVP)**

- `VentaPagada`, `ComprobanteEmitido`, `VehiculoListo`, `CierreCajaCerrado`

---

## 5) Restricciones, índices y validaciones (valor negocio)

**Unicidad y formato**

- `VEHICULO.patente` **única por empresa** `(empresa_id, patente_normalizada)` con normalización (trim, uppercase, sin guiones/espacios).
- `SERVICIO.nombre` **único por empresa** `(empresa_id, nombre_normalizado)` para evitar duplicados.
- `SUCURSAL.codigo_erp` **único por empresa** si se usa mapeo ERP.

**Precios sin solapamiento (simple)**

- En `PRECIO_SERVICIO`, no permitir rangos superpuestos para la misma tupla `(empresa_id, sucursal_id, servicio_id, tipo_vehiculo_id)`.
  - Chequeo: al insertar, validar que `[vigencia_inicio, vigencia_fin]` no colisione con otro rango activo.

**Integridad operacional**

- `VENTA_ITEM.cantidad >= 1`, `precio_unitario >= 0`.
- `PAGO.monto > 0` y no exceder `saldo_pendiente` cuando `es_propina=false`.
- `COMPROBANTE.numero` consecutivo por `(sucursal_id, tipo)` vía `SECUENCIA_COMPROBANTE` + **idempotencia** a nivel de operación de emisión.

**Índices prácticos**

- Búsquedas:
  - `CLIENTE(email)`, `CLIENTE(telefono_wpp)`
  - `VEHICULO(patente_normalizada)`
  - `VENTA(sucursal_id, creado_en)`, `VENTA(estado)`
  - `PAGO(venta_id, pagado_en)`
  - `PRECIO_SERVICIO(sucursal_id, servicio_id, tipo_vehiculo_id, vigencia_inicio)`

---

## 6) Roles (mínimos, MVP)

- **Admin**: todo sobre su empresa (catálogo, usuarios, precios, reportes, cierres).
- **Operador/Cajero**: crear ventas, ítems, pagos, emitir comprobantes, notificar, cerrar caja.
- **Auditor (solo lectura)**: reportes, ventas, cierres, sin modificar.

_(Implementable en Django con `groups`/`permissions` simples.)_

---

## 7) Procesos granulares (Entradas / Salidas / Reglas / Errores)

> **Regla de oro**: cada proceso retorna una **salida clara** y deja **estado consistente**.

### 7.1 Alta/selección de Cliente y Vehículo

- **Entradas**: `empresa_id`, (`cliente_id` _o_ {nombre, apellido, email?, telefono*wpp?}), (`vehiculo_id` \_o* {tipo_vehiculo_id, marca, modelo, patente?})
- **Salidas**: `cliente_id`, `vehiculo_id` (upsert si coincide por teléfono/email y patente)
- **Reglas**: normalizar `telefono_wpp`, `patente`; evitar duplicados.
- **Errores**: formato inválido, patente duplicada, tipo_vehiculo inexistente.

### 7.2 Crear venta (borrador)

- **Entradas**: `empresa_id`, `sucursal_id`, `cliente_id`, `vehiculo_id`
- **Salidas**: `venta_id` (estado=`borrador`, `saldo_pendiente = 0`)
- **Reglas**: sucursal activa, cliente/vehículo pertenecen a la misma empresa.
- **Errores**: referencias cruzadas de otra empresa, sucursal inactiva.

### 7.3 Agregar/editar ítems de venta

- **Entradas**: `venta_id`, lista de `{servicio_id, cantidad}`, **fecha_precio** (default: `now()` del servidor)
- **Salida**: `subtotal`, `total`, `saldo_pendiente` recalculados
- **Reglas**: resolver **precio** en `PRECIO_SERVICIO` por `sucursal + servicio + tipo_vehiculo + fecha_precio`; cachear `servicio_nombre`.
- **Errores**: precio no encontrado, cantidad < 1, servicio inactivo.

### 7.4 Registrar pago(s)

- **Entradas**: `venta_id`, `metodo` (efectivo/tarjeta/MP), `monto`, `es_propina?`, `idempotency_key?`
- **Salida**: `saldo_pendiente` actualizado; posible transición a `pagado` si `saldo_pendiente = 0`.
- **Reglas**: no permitir `monto` > `saldo_pendiente` cuando `es_propina=false`.
- **Errores**: monto inválido, `idempotency_key` repetida (duplicado).

### 7.5 Finalizar venta (trabajo completo)

- **Entradas**: `venta_id`
- **Salida**: `estado=terminado` (o `pagado` si saldo=0)
- **Reglas**: debe existir ≥1 `VENTA_ITEM`.
- **Errores**: venta sin ítems; venta cancelada.

### 7.6 Emitir comprobante (no fiscal)

- **Entradas**: `venta_id`, `tipo`, `punto_venta`, `cliente_facturacion_id?`
- **Salida**: `COMPROBANTE{numero, pdf_url}`
- **Reglas**: reservar número con `SECUENCIA_COMPROBANTE` (transacción + idempotencia); snapshot de totales.
- **Errores**: secuencia bloqueada, venta sin total, venta cancelada.

### 7.7 Notificar cliente (opcional)

- **Entradas**: `venta_id`, `PLANTILLA_NOTIF.clave`
- **Salida**: `LOG_NOTIF{id, estado=enviado|fallido}`
- **Reglas**: render de plantilla con placeholders y datos de la venta.
- **Errores**: canal no habilitado, destinatario vacío.

### 7.8 Cierre de caja

- **Entradas**: `sucursal_id`, `usuario_id`, `rango_horas`
- **Salida**: `CIERRE_CAJA{id}` + `CIERRE_CAJA_TOTAL` agrupado por `metodo`
- **Reglas**: sumar pagos del periodo; propinas separadas.
- **Errores**: solapamiento de cierres, rango vacío.

#### Diagrama de flujo de Cierre (MVP)

```mermaid
flowchart TD
  A["Abrir rango de cierre"]
  B["Recolectar pagos del periodo"]
  C["Sumar por metodo y propinas"]
  D["Registrar Cierre de Caja y Totales"]
  E{"Validar cuadratura"}
  F["Cerrar caja"]
  G["Anotar ajuste o notas y cerrar"]

  A --> B
  B --> C
  C --> D
  D --> E
  E --> F
  E --> G
```

---

## 8) Endpoints MVP (sugeridos, nombres lógicos)

- `/clientes [GET/POST]`, `/vehiculos [GET/POST]`
- `/ventas [POST]` (crear borrador), `/ventas/{id} [GET/PATCH]`
- `/ventas/{id}/items [POST/PATCH/DELETE]`
- `/ventas/{id}/pagos [POST]`
- `/ventas/{id}/finalizar [POST]`
- `/ventas/{id}/comprobante [POST]`
- `/ventas/{id}/notificar [POST]`
- `/cierres [POST]`, `/cierres/{id} [GET]`
- `/precios [GET/POST]`, `/servicios [GET/POST]`

_(En Django: `UUIDField` como PK, `auto_now(_add)` para timestamps, `constraints` en `Meta`.)_

---

## 9) Reportes y KPIs (operativos, MVP)

- **Ventas por día / sucursal** (total, #ventas, ticket promedio)
- **Servicios top** por cantidad y facturación
- **Métodos de pago** (mix por periodo)
- **Propinas** (total y % sobre ventas)
- **Clientes recurrentes** (% repiten en 30/60 días) _(simple: por `vehiculo_id` o `cliente_id`)_

---

## 10) Consideraciones de implementación (Django, prácticas simples)

- **Soft-delete**: usar `eliminado_en` (filtro global por empresa y `eliminado_en IS NULL`).
- **Transactions**: emisión de comprobante y movimientos críticos con `select_for_update()` sobre `SECUENCIA_COMPROBANTE`.
- **Idempotencia**: `PAGO.idempotency_key` y “safe re-try” en emisión de comprobantes.
- **Validación de precios**: función única `resolver_precio(empresa, sucursal, servicio, tipo_vehiculo, fecha)` para centralizar la lógica.
- **Serializadores simples**: exponer sólo campos necesarios a UI.
- **Seeds mínimos**: `TIPO_VEHICULO` comunes (auto, moto, camioneta).

---

## 11) Circuito de una Venta (secuencia)

```mermaid
sequenceDiagram
  participant U as Operador
  participant API as Django_API
  participant DB as PostgreSQL

  U->>API: Seleccionar/crear Cliente y Vehiculo
  API->>DB: Upsert CLIENTE / VEHICULO
  DB-->>API: OK

  U->>API: Crear VENTA (sucursal, cliente, vehiculo)
  API->>DB: Insert VENTA (estado=borrador)
  DB-->>API: VENTA{id}

  U->>API: Agregar servicios (VENTA_ITEM)
  API->>DB: Insert VENTA_ITEM(s) + recalculo totales
  DB-->>API: subtotal, total, saldo

  U->>API: Registrar PAGO(s) (metodo, monto)
  API->>DB: Insert PAGO(s) + actualizar saldo_pendiente
  DB-->>API: saldo actualizado

  U->>API: Finalizar VENTA
  API->>DB: Update VENTA.estado (terminado o pagado)
  DB-->>API: OK

  U->>API: Emitir COMPROBANTE
  API->>DB: Insert COMPROBANTE + numerar (SECUENCIA_COMPROBANTE)
  DB-->>API: numero + pdf_url

  U->>API: Notificar cliente
  API->>DB: Insert LOG_NOTIF (registro del envio)
  DB-->>API: OK
```

---

# Plan detallado por app (Django) — SaaS Lavaderos (MVP)

> Objetivo: que cada app tenga **responsabilidades claras**, **módulos internos** y **flujos** listos para implementar.  
> Convención de diagramas: usar `flowchart` sin etiquetas en aristas para máxima compatibilidad.

---

## 1) `accounts/` (allauth + membresías + roles)

**Rol**: Autenticación (allauth), pertenencia a empresas y autorización por rol.

**Módulos**

- `models.py`: `UserProfile`, `EmpresaMembership(user, empresa, rol)`
- `services.py`: alta empresa + owner, asignación de roles, helpers de autorización
- `serializers.py` (DRF): perfiles y membresías
- `views.py`/`urls.py`: endpoints de perfil y onboarding simple
- `permissions.py`: `IsMemberOfEmpresa`, `HasRole`

```mermaid
flowchart TD
  A[Signup/Login allauth] --> B[Crear UserProfile]
  B --> C[Asociar EmpresaMembership]
  C --> D[Resolver rol efectivo]
  D --> E[Inyectar permisos en request]
```

---

## 2) `org/` (empresa, sucursal, configuración)

**Rol**: Raíz multi-tenant; sucursales; configuración por claves.

**Módulos**

- `models.py`: `EMPRESA`, `SUCURSAL`, `EMPRESA_CONFIG`
- `services.py`: lectura de config, alta sucursal, validaciones
- `serializers.py` y `views.py`: CRUD limitado
- `selectors.py`: queries frecuentes por empresa/sucursal

```mermaid
flowchart TD
  A[Crear EMPRESA] --> B[Crear SUCURSAL inicial]
  B --> C[Guardar EMPRESA_CONFIG claves basicas]
  C --> D[Lectura de config por clave]
```

---

## 3) `customers/` (clientes y datos de facturación)

**Rol**: Gestión de clientes y perfiles fiscales.

**Módulos**

- `models.py`: `CLIENTE`, `CLIENTE_FACTURACION`
- `services.py`: `upsert_cliente`, `get_or_create_facturacion`
- `serializers.py` y `views.py`: endpoints REST
- `normalizers.py`: email/teléfono

```mermaid
flowchart TD
  A[Buscar cliente] --> B{Existe?}
  B -->|No| C[Crear cliente normalizado]
  B -->|Si| D[Actualizar datos]
  C --> E[Opcional: crear facturacion]
  D --> E[Opcional: crear/obtener facturacion]
```

---

## 4) `vehicles/` (tipos y vehículos)

**Rol**: Tipos de vehículo y vehículos por cliente con unicidad de patente por empresa.

**Módulos**

- `models.py`: `TIPO_VEHICULO`, `VEHICULO`
- `services.py`: `upsert_vehiculo`, `normalizar_patente`
- `serializers.py` y `views.py`: endpoints REST
- `validators.py`: unicidad `(empresa_id, patente_normalizada)`

```mermaid
flowchart TD
  A[Recibir datos del vehiculo] --> B[Normalizar patente]
  B --> C{Existe patente en empresa?}
  C -->|No| D[Crear vehiculo]
  C -->|Si| E[Actualizar/Asociar a cliente]
```

---

## 5) `catalog/` (servicios)

**Rol**: Catálogo de servicios.

**Módulos**

- `models.py`: `SERVICIO`
- `services.py`: validación de nombre único por empresa
- `serializers.py`, `views.py`
- `selectors.py`: listar activos

```mermaid
flowchart TD
  A[Alta servicio] --> B[Normalizar nombre]
  B --> C{Nombre unico en empresa?}
  C -->|Si| D[Crear/Activar]
  C -->|No| E[Rechazar/Actualizar existente]
```

---

## 6) `pricing/` (precios efectivos por sucursal/tipo/servicio)

**Rol**: Tarifas con vigencia; resolver precio efectivo.

**Módulos**

- `models.py`: `PRECIO_SERVICIO`
- `services.py`: `resolver_precio`, alta sin solapamientos
- `validators.py`: colisión de rangos
- `serializers.py`, `views.py`

```mermaid
flowchart TD
  A[Alta precio] --> B[Validar rango sin solape]
  B --> C[Guardar precio]
  C --> D[Resolver precio por fecha]
```

---

## 7) `sales/` (ventas e ítems; estados)

**Rol**: Crear venta, gestionar ítems, totales y estados.

**Módulos**

- `models.py`: `VENTA`, `VENTA_ITEM` (métodos de recálculo)
- `services.py`: `crear_venta`, `agregar_items`, `finalizar_venta`
- `calculations.py`: subtotal, total, saldo
- `serializers.py`, `views.py`
- `fsm.py`: transiciones de estado

```mermaid
flowchart TD
  A[Crear venta borrador] --> B[Agregar items]
  B --> C[Recalcular totales]
  C --> D{Saldo 0 y trabajo listo?}
  D -->|Si| E[Marcar pagado]
  D -->|No| F[Marcar terminado o seguir en proceso]
```

---

## 8) `payments/` (pagos e idempotencia)

**Rol**: Registrar pagos, actualizar saldo, transición a pagado.

**Módulos**

- `models.py`: `PAGO`
- `services.py`: `registrar_pago` con `idempotency_key`
- `serializers.py`, `views.py`
- `validators.py`: `monto > 0`, límite por saldo

```mermaid
flowchart TD
  A[Recibir pago] --> B[Validar idempotency]
  B --> C[Guardar pago]
  C --> D[Actualizar saldo venta]
  D --> E{Saldo 0?}
  E -->|Si| F[Marcar venta como pagada]
  E -->|No| G[Venta con saldo pendiente]
```

---

## 9) `invoicing/` (comprobante no fiscal + secuencia)

**Rol**: Emitir comprobante con numeración atómica por sucursal/tipo.

**Módulos**

- `models.py`: `COMPROBANTE`, `SECUENCIA_COMPROBANTE`
- `services.py`: `emitir_comprobante` (`select_for_update` sobre secuencia)
- `pdf.py`: generador PDF simple (placeholder MVP)
- `serializers.py`, `views.py`

```mermaid
flowchart TD
  A[Solicitar emision] --> B[Lock de secuencia]
  B --> C[Obtener numero]
  C --> D[Snapshot totales]
  D --> E[Generar PDF]
  E --> F[Guardar comprobante]
```

---

## 10) `notifications/` (plantillas y logs)

**Rol**: Render de mensajes y registro de envíos.

**Módulos**

- `models.py`: `PLANTILLA_NOTIF`, `LOG_NOTIF`
- `services.py`: `enviar_notificacion(venta, clave_plantilla)`
- `renderers.py`: placeholders estándar
- `serializers.py`, `views.py`

```mermaid
flowchart TD
  A[Seleccionar plantilla] --> B[Render con datos de venta]
  B --> C[Intento de envio]
  C --> D[Registrar LOG_NOTIF con estado]
```

---

## 11) `cashbox/` (cierres de caja)

**Rol**: Consolidar pagos por rango y método; generar cierre + totales.

**Módulos**

- `models.py`: `CIERRE_CAJA`, `CIERRE_CAJA_TOTAL`
- `services.py`: `cerrar_caja(sucursal, desde, hasta)`
- `serializers.py`, `views.py`

```mermaid
flowchart TD
  A[Definir rango] --> B[Recolectar pagos del periodo]
  B --> C[Agrupar por metodo y propina]
  C --> D[Crear CIERRE_CAJA]
  D --> E[Crear CIERRE_CAJA_TOTAL]
  E --> F[Cerrar caja]
```

---

## 12) `saas/` (planes y suscripciones — estructura básica)

**Rol**: Estructura para planes y facturas SaaS (automatización luego).

**Módulos**

- `models.py`: `PLAN_SAAS`, `SUSCRIPCION_SAAS`, `FACTURA_SAAS`, `PAGO_SAAS`
- `services.py`: alta suscripción, emitir factura demo
- `serializers.py`, `views.py`

```mermaid
flowchart TD
  A[Asignar plan] --> B[Crear suscripcion]
  B --> C[Emitir factura periodica]
  C --> D[Registrar pago]
```

---

## 13) `audit/` y `app_log/` (observabilidad mínima)

**Rol**: Auditoría de cambios y logs de eventos.

**Módulos**

- `audit/models.py`: `AUDITORIA_CAMBIO`
- `audit/middleware.py`: captura de cambios CRUD simples
- `app_log/models.py`: `APP_LOG`
- `app_log/services.py`: registrar eventos técnicos/de negocio

```mermaid
flowchart TD
  A[Operacion CRUD] --> B[Capturar diff]
  B --> C[Guardar AUDITORIA_CAMBIO]
  A --> D[Registrar APP_LOG segun nivel]
```

---

## 14) Diagrama de dependencias entre apps (alto nivel)

```mermaid
flowchart LR
  accounts --> org
  accounts --> customers
  accounts --> vehicles
  org --> pricing
  catalog --> pricing
  vehicles --> sales
  customers --> sales
  pricing --> sales
  sales --> payments
  sales --> invoicing
  sales --> notifications
  payments --> cashbox
  invoicing --> notifications
  org --> cashbox
  saas --> org
```

---

## 15) Contratos de servicios (resumen de E/S por app)

- **customers**: `upsert_cliente(empresa, datos)` → `CustomerDTO`
- **vehicles**: `upsert_vehiculo(empresa, cliente, datos)` → `VehicleDTO`
- **pricing**: `resolver_precio(empresa, sucursal, servicio, tipo, fecha)` → `{precio, moneda}`
- **sales**: `crear_venta(...)` → `VentaDTO`; `agregar_items(venta, items, fecha)` → `VentaDTO`; `finalizar_venta(venta)` → `VentaDTO`
- **payments**: `registrar_pago(venta, metodo, monto, es_propina?, key?)` → `VentaDTO`
- **invoicing**: `emitir_comprobante(venta, tipo, pv, cf?)` → `ComprobanteDTO`
- **notifications**: `enviar_notificacion(venta, plantilla)` → `log_id`
- **cashbox**: `cerrar_caja(empresa, sucursal, desde, hasta)` → `CierreCajaDTO`

---

## 16) Reglas transversales (mínimas y prácticas)

- **Multitenancy**: `empresa_id` obligatorio en todo; filtros por defecto en managers.
- **Estados de venta**: transiciones controladas; no finalizar sin ítems.
- **Idempotencia** en pagos y emisión de comprobantes (lock de secuencia).
- **Validación de precios**: sin solapamiento por tupla `(empresa, sucursal, servicio, tipo)`.
- **Unicidades**: patente por empresa; servicio por nombre normalizado y empresa.

---

# LavaderosApp — Documentación de **Estructura General**

> **Objetivo**: Establecer la arquitectura de carpetas, los layouts de UI y las convenciones transversales del proyecto.  
> **Alcance**: Estructura global, _no_ de cada módulo; dejamos listo el terreno para seguir “app por app”.  
> **Stack**: Django (server-rendered) + Bootstrap 5 (tema Bootswatch local). **Sin DRF**.

---

## 1) Árbol del proyecto (actualizado)

```bash
lavaderosapp/
├── manage.py
├── .env
├── .gitignore
├── README.md
├── lavaderos/
│   ├── __init__.py
│   ├── urls.py                      # enrutamiento global (incluye urls de apps)
│   ├── tenancy.py                   # utilidades multi-tenant (subdominio/header) [opcional]
│   ├── middleware.py                # TenancyMiddleware: inyecta empresa/sucursal en request
│   ├── permissions.py               # permisos/roles reutilizables a nivel proyecto
│   └── settings/
│       ├── __init__.py
│       ├── base.py                  # base común a todos los entornos
│       ├── development.py           # DEBUG, sqlite, email consola
│       ├── production.py            # Postgres, seguridad, SMTP real
│       └── render.py                # ajustes para Render.com (si aplica)
├── templates/                       # templates globales + overrides de librerías
│   ├── base.html                    # layout PÚBLICO (landing, marketing, login/signup)
│   ├── base_auth.html               # layout AUTENTICADO (navbar compacto + sidebar)
│   ├── home_dashboard.html          # panel contextual para usuarios logueados
│   ├── includes/
│   │   ├── _navbar_public.html      # navbar público (CTA de login/signup)
│   │   ├── _navbar_auth.html        # navbar autenticado (perfil, membresías, salir)
│   │   ├── _sidebar.html            # menú lateral principal (apps, selector de sucursal)
│   │   ├── _messages.html           # Django messages (alerts Bootstrap)
│   │   ├── _footer.html             # pie de página
│   │   └── _pagination.html         # componente reutilizable de paginación
│   ├── account/                     # overrides de django-allauth
│   │   ├── login.html
│   │   ├── signup.html
│   │   ├── password_reset.html
│   │   ├── password_reset_done.html
│   │   ├── password_reset_from_key.html
│   │   ├── password_reset_from_key_done.html
│   │   ├── password_change.html
│   │   └── password_change_done.html
│   └── errors/                      # páginas de error personalizadas
│       ├── 401.html
│       ├── 403.html
│       ├── 404.html
│       └── 500.html
├── static/                          # assets globales versionados
│   ├── css/
│   │   ├── bootswatch/brite.min.css # tema Bootstrap local
│   │   └── app.css                  # reservado para estilos propios (mínimos)
│   ├── js/
│   │   ├── bootstrap.bundle.min.js  # Bootstrap + Popper
│   │   └── app.js                   # scripts globales (inicializaciones)
│   ├── img/
│   │   └── logo.png
│   └── vendor/                      # librerías opcionales (bootstrap-icons, chart.js, etc.)
├── media/                           # uploads en desarrollo (en prod: storage externo)
├── staticfiles/                     # destino de collectstatic (no editar a mano)
└── apps/                            # **todas** las apps de dominio
    ├── accounts/                    # auth (allauth), perfil, membresías
    ├── org/                         # lavadero (Empresa), Sucursal, selector
    ├── customers/
    ├── vehicles/
    ├── catalog/
    ├── pricing/
    ├── sales/
    ├── payments/
    ├── invoicing/
    ├── notifications/
    ├── cashbox/
    ├── saas/                        # planes/limitaciones (ej. 1 empresa por usuario)
    ├── audit/
    └── app_log/
```

> **Regla de oro**: los templates de cada app viven en `apps/<app>/templates/<app>/**`. Así evitamos colisiones de nombres y mantenemos aislamiento por dominio.

---

## 2) Layouts y herencia de templates

### 2.1 `templates/base.html` (público)

- **Uso**: landing/marketing, login/signup y páginas no autenticadas.
- **Bloques clave**: `title`, `meta_description`, `navbar`, `hero`, `content`, `extra_css`, `extra_js`, `footer`.
- **Navbar**: incluye `includes/_navbar_public.html` (sobrescribir `block navbar` si se desea otra cabecera).
- **Hero**: bloque opcional; se puede anular con `{% block hero %}{% endblock %}`.

### 2.2 `templates/base_auth.html` (autenticado)

- **Uso**: toda página tras login.
- **Composición**:
  - Navbar compacto: `includes/_navbar_auth.html` (perfil, membresías, logout).
  - **Layout con sidebar**:
    - Columna fija con `includes/_sidebar.html` (menú acordeón y **selector de sucursal**).
    - Contenedor principal para `{% block content %}`.
- **Mensajes**: `_messages.html` integrado antes del contenido.

### 2.3 `templates/home_dashboard.html`

- **Uso**: panel contextual tras login.
- **Lógica de presentación** (sin entrar al código):
  - Sin lavadero → CTA “Crear lavadero”.
  - Con lavadero pero sin sucursales → CTA “Crear primera sucursal”.
  - “Listo para operar” (≥ 1 sucursal) → accesos rápidos y widgets placeholder (KPIs).

---

## 3) Partials globales (includes)

- **`_navbar_public.html`**: marca + CTAs “Ingresar” / “Crear cuenta”. Sin enlaces de operación.
- **`_navbar_auth.html`**: avatar/nombre, accesos a **Perfil**, **Membresías**, **Cambiar contraseña** y **Salir**. Navegación funcional se deriva al **sidebar**.
- **`_sidebar.html`**:
  - Encabezado: **Lavadero actual** (empresa activa).
  - **Selector de Sucursal** (`<select>` con `onchange=submit`) que hace **POST** a una ruta de selector (centraliza la fijación en sesión).
  - Acordeones: Organización, Operación, Maestros, Reportes, Administración (links preparados; algunos módulos aún en desarrollo).
- **`_messages.html`**: renderiza `django.contrib.messages` a Bootstrap alerts.
- **`_pagination.html`**: tabla/listados con paginación consistente.
- **`_footer.html`**: pie común (legal/links).

> **Convención**: cualquier página autenticada que necesite navegación de negocio **debe** extender `base_auth.html` para heredar sidebar y mensajes.

---

## 4) Estáticos (static/) y assets

- **Bootstrap**: tema **Bootswatch “brite”** local (`static/css/bootswatch/brite.min.css`).  
  No dependemos de CDNs.
- **JS**: `bootstrap.bundle.min.js` + `app.js` para inicializaciones (por ejemplo, tooltips).
- **Imágenes**: `static/img/` (logo, íconos básicos).
- **Vendor**: espacio para librerías de terceros sin NPM (p. ej., `bootstrap-icons/`).
- **Producción**: ejecutar `collectstatic` → servir `staticfiles/` (Nginx u otro).

---

## 5) Settings y middleware (resumen de integración)

- `INSTALLED_APPS` (clave):
  - `django.contrib.sites`, `allauth`, `allauth.account`
  - Apps propias (`apps.org`, `apps.accounts`, …)
  - `SITE_ID = 1`
- `MIDDLEWARE`:
  - **`lavaderos.middleware.TenancyMiddleware`** (inyecta `request.empresa_activa` y `request.sucursal_activa` desde sesión; si falta, intenta fijar por defecto la primera empresa del usuario).
- `TEMPLATES`:
  - `DIRS = [BASE_DIR / "templates"]`
  - `context_processors.request` **habilitado** (requerido por allauth y varios templates).
- Allauth (email-only recomendado en MVP):
  - `ACCOUNT_AUTHENTICATION_METHOD="email"`
  - `ACCOUNT_EMAIL_REQUIRED=True`
  - `ACCOUNT_EMAIL_VERIFICATION="none"` (en prod real: `"mandatory"`)
  - `ACCOUNT_USERNAME_REQUIRED=False`
  - `ACCOUNT_LOGOUT_ON_GET=True`
  - `LOGIN_REDIRECT_URL="/"`, `LOGOUT_REDIRECT_URL="/"`

---

## 6) Convenciones por app (estructura recomendada)

Cada módulo en `apps/<app>/` sigue este patrón (MVP):

```bash
apps/<app>/
├── __init__.py
├── apps.py
├── admin.py
├── migrations/
│   └── __init__.py
├── models.py
├── urls.py
├── views.py                     # CBVs; delgadas; usan services/selectors
├── forms/
│   ├── __init__.py
│   └── <app>.py
├── services/
│   ├── __init__.py
│   └── casos_de_uso.py          # lógica de dominio (crear/editar, etc.)
├── selectors.py                 # lecturas/queries para vistas
├── permissions.py               # reglas de acceso/roles específicas del app
├── templates/<app>/             # templates namespaced de la app
│   └── ...
└── static/<app>/                # assets propios del módulo
    └── ...
```

**Principios**:

- **Separation of concerns**: vistas delgadas; mutaciones en `services/`, lecturas en `selectors.py`.
- **Templates con Bootstrap** directo (solo clases en HTML; sin CSS custom salvo casos puntuales).
- **Nombres namespaced** (`templates/<app>/**`) para evitar choques entre apps.

---

## 7) Ruteo global y convenciones de URL

- `lavaderos/urls.py` incluye:
  - `/accounts/` (django-allauth)
  - Rutas de **accounts** propias (perfil, membresías), p. ej.: `/cuenta/perfil/`, `/cuenta/membresias/`
  - Rutas por **app** con prefijos claros (`/org/...`, `/clientes/...`, etc.).
- **Nombrado**: `app_namespace:view_name` (p. ej., `org:sucursales`), para usar con `{% url %}` sin ambigüedad.

---

## 8) Tenancy (multi-tenant simplificado)

- **Plan estándar**: 1 empresa por usuario (controlado desde `apps/saas/` o settings).
- **Sesión**:
  - `empresa_id`: lavadero activo
  - `sucursal_id`: sucursal activa dentro del lavadero
- **TenancyMiddleware**:
  - Carga `request.empresa_activa` / `request.sucursal_activa`.
  - Si `empresa_id` no existe y el usuario tiene empresas, fija la **primera** por defecto.
  - Si `sucursal_id` no pertenece a la empresa activa, se limpia.
- **Selector centralizado**: un único endpoint que recibe `POST` con `sucursal` (y, en planes superiores, `empresa`) para actualizar la sesión.

> Esto permite que **cualquier** vista pueda suponer un contexto consistente (`request.empresa_activa`, `request.sucursal_activa`) sin duplicar lógica.

---

## 9) Accesibilidad, SEO y calidad

- **A11y**: skip link, labels, `autocomplete` en formularios, colores y contrastes por Bootstrap.
- **SEO meta** en `base.html`: `title`, `description`, Open Graph y Twitter Cards con valores por defecto y bloques sobrescribibles.
- **Mensajería** clara: usar `django.contrib.messages` para éxitos y errores de validación/flujo.
- **Errores**: páginas personalizadas en `templates/errors/` (401/403/404/500).

---

## 10) Cómo agregar una página nueva (checklist)

1. Elegí layout: **público** (`base.html`) o **autenticado** (`base_auth.html`).
2. Creá el template en `apps/<app>/templates/<app>/mi_pagina.html` y extendé el layout correspondiente.
3. Agregá la **CBV** en `views.py` y la ruta en `urls.py` del app (namespace).
4. Si la página necesita navegación del sistema, usa **`base_auth.html`** para heredar sidebar.
5. Mostrá feedback con `messages` y, si es un form, **errores de campo y `non_field_errors`**.
6. (Opcional) Añadí assets específicos en `apps/<app>/static/<app>/` y referencialos con `{% static %}`.

---

# Módulo 1 — `apps/accounts` (Autenticación, Perfil y Membresías)

> **Objetivo:** Integrar **django-allauth** (login/registro/cierre de sesión y recuperación de clave), exponer vistas server-rendered para **Perfil** y **Membresías**, y modelar la relación **Usuario ↔ Empresa (rol)** del SaaS.  
> **Fuera de alcance:** alta/edición de Empresa/Sucursal (vive en `apps/org`) y flujos de operación/ventas.

---

## 1) Estructura del módulo (MVP final)

```
apps/accounts/
├─ __init__.py
├─ apps.py
├─ admin.py
├─ migrations/
│  └─ __init__.py
├─ models.py                  # EmpresaMembership (User↔Empresa, rol)
├─ urls.py                    # /cuenta/perfil/, /cuenta/membresias/
├─ views.py                   # ProfileView, MembershipListView (server-rendered)
├─ forms/
│  ├─ __init__.py             # Login/Signup + Reset/Set/Change Password (Bootstrap)
│  └─ profile.py              # ProfileForm (Bootstrap)
├─ services/
│  ├─ __init__.py
│  ├─ memberships.py          # ensure_membership, cambio de rol
│  └─ profile.py              # update_user_profile
├─ selectors.py               # memberships_for(user), etc.
├─ permissions.py             # helpers de rol (admin/operador/auditor)
├─ templates/
│  └─ accounts/
│     ├─ profile.html
│     ├─ memberships.html
│     └─ _profile_form.html
```

### Estructura global de templates (overrides + layout)

```
templates/
├─ base.html
├─ includes/
│  ├─ _navbar.html            # menú Cuenta, selector de empresa, logout
│  └─ _messages.html          # alerts Bootstrap (django.messages)
└─ account/                   # overrides de allauth (sin “s”)
   ├─ login.html
   ├─ signup.html
   ├─ password_reset.html
   ├─ password_reset_done.html
   ├─ password_reset_from_key.html
   ├─ password_reset_from_key_done.html
   ├─ password_change.html            # ambio estando logueado
   └─ password_change_done.html
```

---

## 2) Qué hace cada cosa (resumen ejecutivo)

- **`models.py`**: `EmpresaMembership(user, empresa, rol)` con unicidad `(user, empresa)`.
- **`forms/__init__.py`**: _todos_ los formularios clave de allauth (login, signup, reset, set, change) inyectan clases Bootstrap a widgets (`form-control`, `form-select`, `form-check-input`) y placeholders/`autocomplete`.
- **`forms/profile.py`**: `ProfileForm` con el mismo patrón Bootstrap.
- **`views.py`**: vistas delgadas; mutaciones en **services**, lecturas en **selectors**.
- **`services/*`**: casos de uso (perfil y membresías), con logging mínimo.
- **`selectors.py`**: consultas para vistas/UX (p.ej., membresías del usuario).
- **`templates/account/*`**: todos los flujos de allauth con el layout de `base.html`.
- **`_messages.html`**: muestra feedback como alerts.
- **`_navbar.html`**: accesos a Perfil, Membresías, Selector de empresa y Logout.

> **Principio:** vistas finas; lógica en services/selectors; estilos Bootstrap desde los **forms** (no repetimos clases en cada template).

---

## 3) Settings esenciales (lo mínimo para que funcione igual en todos los entornos)

```python
INSTALLED_APPS += [
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "apps.org",        # debe migrar antes que accounts (FK)
    "apps.accounts",
]
SITE_ID = 1

MIDDLEWARE += [
    "allauth.account.middleware.AccountMiddleware",  # requerido por allauth reciente
]

TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]
# ¡Importante! para allauth:
# "django.template.context_processors.request" debe estar en context_processors

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Email-only login (MVP)
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "none"   # en prod real: "mandatory"
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_LOGOUT_ON_GET = True          # logout inmediato (sin logout.html)
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

ACCOUNT_FORMS = {
    "login": "apps.accounts.forms.LoginForm",
    "signup": "apps.accounts.forms.SignupForm",
    "reset_password": "apps.accounts.forms.ResetPasswordForm",
    "reset_password_from_key": "apps.accounts.forms.ResetPasswordKeyForm",
    "change_password": "apps.accounts.forms.ChangePasswordForm",  # opcional
}
```

---

## 4) Rutas y vistas (qué URL usa qué template)

**Allauth (ya provisto, con nuestros overrides):**

- `/accounts/login/` → `account/login.html`
- `/accounts/signup/` → `account/signup.html`
- `/accounts/logout/` → inmediato si `ACCOUNT_LOGOUT_ON_GET=True` (sin template)
- `/accounts/password/reset/` → `account/password_reset.html`
- `/accounts/password/reset/done/` → `account/password_reset_done.html`
- `/accounts/password/reset/key/<uidb36>-<key>/` → `account/password_reset_from_key.html`
- `/accounts/password/reset/key/done/` → `account/password_reset_from_key_done.html`
- `/accounts/password/change/` → `account/password_change.html` _(opcional)_
- `/accounts/password/change/done/` → `account/password_change_done.html` _(opcional)_

**Accounts (esta app):**

- `/cuenta/perfil/` → perfil (GET/POST)
- `/cuenta/membresias/` → listado de empresas y rol; botón **“Activar”** → `/org/seleccionar/?empresa=<id>`

---

## 5) Modelado de membresías (multi-tenant)

- `EmpresaMembership(user, empresa, rol)` con choices (`admin`, `operador`, `auditor`).
- Un registro **único por (user, empresa)**.
- **Dependencia**: `org.Empresa` debe existir y migrar **antes**.
- Uso en UI: `memberships.html` linkea al selector `/org/seleccionar/`.

---

## 6) UX / UI (convenciones)

- **Bootstrap 5** global en `base.html` (tema Bootswatch ok).
- **Mensajes** → `_messages.html` (alerts).
- **Navbar** → `_navbar.html` con acciones de cuenta y chip de empresa activa (si `empresa_id` en sesión).
- **Accesibilidad**: labels y `autocomplete` correctos; placeholders coherentes.

---

## 7) Seguridad / permisos

- Vistas del módulo → requieren **usuario autenticado**.
- No se mutan empresas ni roles desde `accounts`.
- CSRF por defecto en formularios server-rendered.
- Reutilizar `permissions.py` donde aplique.

---

## 8) Pasos de verificación rápida

1. Migrar `org` y `accounts` (en ese orden).
2. Crear una **Empresa** en admin y asignar membresía al usuario.
3. Probar: signup → login → perfil → membresías → activar empresa.
4. Probar “¿Olvidaste tu contraseña?” en login:
   - reset → done → link email → set password → done.

---

## 9) Estado actual y próximos pasos

- **Estado**: `accounts` completo (allauth con Bootstrap, perfil, membresías, integración con selector de `org`).
- **Siguiente**: `apps/org` CRUD Empresa/Sucursal y middleware de tenancy (inyectar `empresa_activa` en request/plantillas).
- **Producción**: valorar `ACCOUNT_EMAIL_VERIFICATION="mandatory"` y backend SMTP real.

> **Decisión registrada:** estilos centralizados en **forms**; overrides de templates en `templates/account/`; vistas delgadas con lógica en services/selectors. La selección de empresa vive en `org` y se invoca desde “Membresías”.

# Módulo 2 — `apps/org` (Lavadero/Empresa, Sucursales, Empleados y Contexto)

> **Objetivo:** Modelar **Lavadero (Empresa)** y **Sucursales**, proveer el **onboarding** (crear lavadero → crear sucursal), mantener el **contexto activo** (empresa/sucursal) y permitir a la empresa **gestionar empleados y permisos**.  
> **Alcance:** Django server-rendered (sin DRF), CBVs, Bootstrap 5, permisos centralizados.  
> **Integración SaaS:** límites y suscripciones se resuelven vía `apps.saas` (`limits.py`, `services/subscriptions.py`).

---

## 1) Estructura del módulo (actualizada)

```
apps/org/
├─ __init__.py
├─ apps.py
├─ admin.py
├─ migrations/
│  └─ __init__.py
├─ models.py                 # Empresa, EmpresaConfig (opcional), Sucursal
├─ urls.py                   # /org/...
├─ views.py                  # CBVs: empresas, sucursales, empleados, selector, post-login
├─ forms/
│  ├─ __init__.py
│  └─ org.py                 # EmpresaForm, SucursalForm, EmpleadoForm
├─ services/
│  ├─ __init__.py
│  ├─ empresa.py             # (opcional)
│  └─ sucursal.py            # (opcional)
├─ selectors.py              # empresas_para_usuario, etc. (sin hardcode de límites)
├─ permissions.py            # Perm, ROLE_POLICY, mixins (centraliza permisos)
├─ templatetags/
│  ├─ __init__.py
│  └─ org_perms.py           # {% can "perm.code" %} en templates
├─ templates/
│  └─ org/
│     ├─ empresas.html
│     ├─ empresa_form.html
│     ├─ sucursales.html
│     ├─ sucursal_form.html
│     ├─ empleados.html
│     └─ empleado_form.html
├─ static/
│  └─ org/
│     ├─ org.js
│     └─ org.css
└─ emails/
   └─ empresa_created.txt    # (opcional)
```

**Notas de diseño**

- **Vistas delgadas**: permisos en `permissions.py`; vistas declaran `required_perms`.
- **Bootstrap** en templates; forms “limpios”.
- **Onboarding** guiado (signup → empresa → primera sucursal).
- **Límites por plan**: ya **no** se usan constantes en `settings`. Todo gating pasa por `apps.saas.limits` y la suscripción activa de la empresa.

---

## 2) Modelos (resumen)

### `Empresa`

- `nombre`, `subdominio` (único), `logo`, `activo`, timestamps.
- Relaciones: `memberships` (`accounts.EmpresaMembership`), `sucursales`, **`suscripcion` (OneToOne con `saas.SuscripcionSaaS`)**.
- Se fija en sesión como `empresa_id`.

### `Sucursal`

- `empresa` (FK), `nombre`, `direccion` (opcional), `codigo_interno` (único por empresa, **autogenerado en `save()`**).
- Se fija como `sucursal_id`.

### `EmpresaConfig` (opcional)

- Par `clave/valor` JSON por empresa.

---

## 3) Formularios (`forms/org.py`)

- `EmpresaForm`: `nombre`, `subdominio`, `logo`, `activo` (en alta, forzado a `True`).
- `SucursalForm`: `nombre`, `direccion` (sin `codigo_interno`).
- `EmpleadoForm`: `email`, `rol` (`admin`/`operador`), `sucursal_asignada`, `password_inicial` (solo crear).

---

## 4) Permisos centralizados (`permissions.py`)

- **`Perm`**:
  - `ORG_VIEW`, `ORG_EMPRESAS_MANAGE`, `ORG_SUCURSALES_MANAGE`, `ORG_EMPLEADOS_MANAGE`
  - (extensibles: `CATALOG_SERVICES_MANAGE`, `CATALOG_PRICES_MANAGE`, etc.)
- **`ROLE_POLICY`** define permisos por rol (admin/operador/…).
- **Mixins**:
  - `EmpresaPermRequiredMixin` resuelve **contexto** y **membership** y valida `required_perms`.
  - Evita loops con `SAFE_VIEWNAMES`.
- **Helper**:
  - `has_empresa_perm(user, empresa, perm)`.

---

## 5) Gating por Plan (integración con `apps.saas`)

- Consultas de límite vía **`apps.saas.limits`**:
  - `can_create_empresa(user)`
  - `can_create_sucursal(empresa)`
  - `can_add_usuario_a_empresa(empresa)`
  - `can_add_empleado(sucursal)`
- **Enforcement**:
  - **Soft** (por defecto): se **muestra mensaje** y se **deshabilitan CTAs** en UI; el `POST` valida y devuelve alerta si no corresponde.
  - **Hard** (`settings.SAAS_ENFORCE_LIMITS = True`): además del mensaje, **se bloquean las creaciones** en los `POST`.
- **Suscripción por defecto**:
  - Tras crear empresa, se llama a `ensure_default_subscription_for_empresa(empresa)` para asignar plan default (con trial si corresponde).

---

## 6) Vistas (CBVs) y comportamiento

- **`EmpresaListView`** (`/org/empresas/`): `required_perms = (ORG_VIEW,)`  
  Muestra “Mi Lavadero”. Contexto incluye `puede_crear_empresa` y `gate_empresa_msg` (desde `can_create_empresa(user)`).

- **`EmpresaCreateView`** (`/org/empresas/nueva/`): onboarding  
  Valida con `can_create_empresa(user)`. Crea `Empresa` + `EmpresaMembership` (**OWNER/ADMIN/ACTIVA**), setea sesión y ejecuta `ensure_default_subscription_for_empresa`. Redirige a crear primera sucursal.

- **`EmpresaUpdateView`**: `ORG_EMPRESAS_MANAGE`.

- **`SucursalListView`**: `ORG_VIEW`  
  Lista sucursales y pasa `puede_crear_sucursal` / `gate_sucursal_msg` desde `can_create_sucursal(empresa)`.

- **`SucursalCreateView`**: `ORG_SUCURSALES_MANAGE`  
  Valida con `can_create_sucursal(empresa)`; primera sucursal → redirige a `/` con “Listo para operar”; si no, vuelve a `/org/sucursales/`.

- **`SucursalUpdateView`**: `ORG_SUCURSALES_MANAGE`.

- **`EmpleadoListView`**: `ORG_EMPLEADOS_MANAGE`  
  Pasa `puede_agregar_empleado` / `gate_empleado_msg` (empresa).

- **`EmpleadoCreateView`**: `ORG_EMPLEADOS_MANAGE`  
  GET: calcula `can_add_usuario_a_empresa(empresa)` para la UI.  
  POST: valida `can_add_usuario_a_empresa(empresa)` y, si hay sucursal, `can_add_empleado(sucursal)`. Crea/actualiza `User` + `EmpresaMembership`.

- **`EmpleadoUpdateView`**: `ORG_EMPLEADOS_MANAGE` (no edita `owner`).

- **`EmpleadoResetPasswordView` / `EmpleadoToggleActivoView` / `EmpleadoDestroyUserView`**: `ORG_EMPLEADOS_MANAGE` (con protecciones: no `owner`, no auto-eliminarse, etc.).

- **`SelectorEmpresaView`**: segura, sanea sesión, activa empresa/sucursal.

- **`PostLoginRedirectView`**: decide onboarding o panel según membership/sucursales.

---

## 7) URLs (namespace `org`) — **incluye empleados**

```
/org/empresas/                      name="org:empresas"
/org/empresas/nueva/                name="org:empresa_nueva"
/org/empresas/<int:pk>/editar/      name="org:empresa_editar"

# Sucursales
/org/sucursales/                    name="org:sucursales"
/org/sucursales/nueva/              name="org:sucursal_nueva"
/org/sucursales/<int:pk>/editar/    name="org:sucursal_editar"

# Empleados
/org/empleados/                     name="org:empleados"
/org/empleados/nuevo/               name="org:empleado_nuevo"
/org/empleados/<int:pk>/editar/     name="org:empleado_editar"
# Acciones POST-only
/org/empleados/<int:pk>/reset-pass/ name="org:empleado_reset_pass"
/org/empleados/<int:pk>/toggle/     name="org:empleado_toggle"
/org/empleados/<int:pk>/eliminar/usuario/  name="org:empleado_eliminar_usuario"

# Selector
/org/seleccionar/                   name="org:selector"
```

---

## 8) Templates (UI/UX + permisos + límites)

- Siempre cargar `{% load org_perms %}` cuando haya CTAs condicionados.
- Mostrar **mensajes** con `{% include "includes/_messages.html" %}` (ya en `base_auth.html`).
- Variables de gating usadas por UI (cuando la vista las provee):
  - `puede_crear_empresa`, `gate_empresa_msg`
  - `puede_crear_sucursal`, `gate_sucursal_msg`
  - `puede_agregar_empleado`, `gate_empleado_msg`
- Ejemplos:
  - `org/empresas.html`: “Nueva sucursal” visible si permiso y si `puede_crear_sucursal`.
  - `org/sucursales.html`: banner informativo cuando no se puede crear más.
  - `org/empleados.html` / `org/empleado_form.html`: botón “Nuevo/Crear empleado” deshabilitado si no se puede.

---

## 9) Sesión y Middleware (Tenancy)

- Claves: `empresa_id`, `sucursal_id`.
- `TenancyMiddleware` inyecta `request.empresa_activa` / `request.sucursal_activa`; limpia inconsistencias.
- `SelectorEmpresaView` evita loops.

---

## 10) Seguridad y reglas

- Solo **miembros activos** operan en una empresa.
- `owner`: no editable/deshabilitable/eliminable desde UI de empleados.
- Acciones destructivas: **POST-only** + **CSRF** + **modales**.
- Si una membresía queda inactiva y el usuario no tiene otras activas, se marca `user.is_active=False`.

---

## 11) Onboarding (secuencia)

```mermaid
sequenceDiagram
  participant U as Usuario
  participant WEB as Vistas Django
  participant DB as DB

  U->>WEB: /accounts/signup -> login
  WEB-->>U: redirect / (Panel)

  alt sin lavadero
    U->>WEB: POST /org/empresas/nueva/
    WEB->>DB: create Empresa + EmpresaMembership(admin)
    DB-->>WEB: Empresa {id}
    note over WEB,U: session.empresa_id = id
    WEB-->>U: redirect /org/sucursales/nueva/
  end

  U->>WEB: POST /org/sucursales/nueva/
  WEB->>DB: create Sucursal(empresa_id = session.empresa_id)
  DB-->>WEB: Sucursal {id}

  alt primera sucursal
    WEB-->>U: redirect /(Panel) + success Listo para operar
  else mas sucursales
    WEB-->>U: redirect /org/sucursales/ + success
  end

  U->>WEB: Sidebar -> POST sucursal=[id] a /org/seleccionar/
  WEB->>DB: validar sucursal pertenece a empresa_activa
  DB-->>WEB: OK
  note over WEB,U: session.sucursal_id = id
  WEB-->>U: success seleccion de sucursal
```

---

## 12) Planes (SaaS) — **(actualizado)**

- **Límites por plan** en `saas.PlanSaaS` (p. ej., `max_sucursales_por_empresa`, `max_usuarios_por_empresa`, `max_empleados_por_sucursal`, etc.).
- **Gating centralizado** en `saas/limits.py`:
  - `can_create_empresa(user)`
  - `can_create_sucursal(empresa)`
  - `can_add_usuario_a_empresa(empresa)`
  - `can_add_empleado(sucursal)`
  - Cada función retorna un objeto con `message` y `should_block()`.
- **Enforcement**:
  - `SAAS_ENFORCE_LIMITS = False` (default “soft”: solo avisos, la vista decide).
  - Si `True`: los `POST` deben **bloquear** creaciones cuando `should_block()` sea `True`.
- **Suscripciones**:
  - `SuscripcionSaaS` (1:1 con Empresa) define `estado`, `payment_status`, `vigente`, `is_trialing`, etc.
  - Onboarding llama `ensure_default_subscription_for_empresa(empresa)` para asignar plan **default** (con `trial_days` si corresponde).

> **Eliminado:** `SAAS_MAX_EMPRESAS_POR_USUARIO`. No se usa más hardcode; todo sale del **Plan vigente**.

---

## 13) Auditoría y datos históricos

- Al **eliminar usuario**, solo se borra el `User` y sus `EmpresaMembership`.  
  **Registros de negocio** (ventas, etc.) deben quedar ligados a la **empresa/sucursal**, no al usuario, o con FK `SET_NULL` + campos de “autor” denormalizados (ej. `autor_email`, `autor_nombre`).  
  → Recomendado para MVP: usar FK `SET_NULL` y denormalizar autor en entidades críticas para preservar historial.

## 14) Errores comunes

- **No se ven avisos de límites** → asegurarse de incluir `_messages.html` y de pasar las variables `puede_*`/`gate_*` desde las vistas (ya contemplado en nuestras vistas).
- **Se puede crear más allá del plan** → verificar `SAAS_ENFORCE_LIMITS` y que los `POST` llamen a `limits.*` (hecho).

---

## 15) Extensiones previstas

- Nuevos permisos: `CATALOG_SERVICIOS_MANAGE`, `CATALOG_PRECIOS_MANAGE` (para permitir operadores que gestionen catálogo pero no sucursales/empleados).
- Invitaciones por correo con token (alta de empleados sin setear password directo).
- Auditoría (quién hizo qué/cuándo) y logs por empresa.

---

### Resumen ejecutivo

- **Gating por plan 100% centralizado** en `apps.saas` (nada hardcodeado en `org`).
- **UI consciente de límites**: muestra banners y deshabilita CTAs cuando corresponde.
- **Enforcement conmutable** (`SAAS_ENFORCE_LIMITS`) sin tocar vistas.

# Módulo 3 — `apps/customers` (Clientes)

> **Objetivo del módulo:** Administrar los datos de los clientes (contacto, cumpleaños, notas internas). Este módulo provee la información base para asociar clientes a vehículos, ventas y notificaciones.

---

## 1) Estructura de carpetas/archivos

```
apps/customers/
├─ __init__.py
├─ apps.py                   # Config de la app (name="apps.customers")
├─ admin.py                  # Registro de Cliente en admin
├─ migrations/
│  └─ __init__.py
├─ models.py                 # Modelo Cliente
├─ urls.py                   # Rutas propias (listado, alta, edición, detalle)
├─ views.py                  # Vistas server-rendered CRUD de clientes
├─ forms/
│  ├─ __init__.py
│  └─ customer.py            # Formulario CustomerForm (validaciones + normalizaciones)
├─ services/
│  ├─ __init__.py
│  └─ customers.py           # Casos de uso: crear/editar cliente
├─ selectors.py              # Lecturas: buscar cliente por nombre/teléfono/email
├─ normalizers.py            # Normalización de datos (email, documento, teléfono, capitalización)
├─ templates/
│  └─ customers/
│     ├─ list.html           # Listado de clientes + búsqueda
│     ├─ form.html           # Alta/edición de cliente
│     ├─ detail.html         # Detalle con datos del cliente (extensible a vehículos/ventas)
│     └─ _form_fields.html   # Partial con los campos (incluible en alta/edición)
├─ static/
│  └─ customers/
│     ├─ customers.css       # Estilos propios (mínimos)
│     └─ customers.js        # Mejoras UX (placeholder para búsqueda/validaciones simples)
└─ emails/
   └─ birthday.txt           # (Opcional) plantilla de felicitación de cumpleaños
```

### Rol de cada componente

- **`models.py`**: define `Cliente` (nombre, apellido, email, teléfono WhatsApp, fecha_nac, dirección, etc.) y campos auxiliares (`tags`, `notas`, `activo`).
- **`forms/customer.py`**: `CustomerForm` con:
  - inyección de clases Bootstrap,
  - normalización de email, documento, teléfono,
  - guardado con empresa activa y usuario creador,
  - conversión de `tags` a lista.
- **`services/customers.py`**: mutaciones de dominio (crear/editar cliente).
- **`selectors.py`**: consultas de lectura (`buscar_cliente(q)`).
- **`normalizers.py`**: helpers para normalizar input (email, documento, teléfono a E.164, capitalizar textos).
- **`views.py`**: CRUD basado en `ListView`, `CreateView`, `UpdateView`, `DetailView`. Incluye vistas para activar/desactivar cliente.
- **`templates/customers/*`**: interfaz UI (listado, formulario, detalle). `_form_fields.html` maneja validación y muestra correctamente `fecha_nac`.

---

## 2) Endpoints implementados

- `/clientes/` → Listado + búsqueda de clientes.
- `/clientes/nuevo/` → Alta de cliente.
- `/clientes/<id>/editar/` → Edición de cliente.
- `/clientes/<id>/detalle/` → Detalle de cliente (con notas y estado activo/inactivo).
- `/clientes/<id>/desactivar/` → POST para desactivar cliente.
- `/clientes/<id>/activar/` → POST para reactivar cliente.
- `/clientes/<id>/eliminar/` → (opcional, solo admin, con confirmación).

---

## 3) Contratos de entrada/salida

### Alta Cliente

- **Input (POST)**: nombre, apellido, email, tel_wpp, fecha_nac, dirección, notas, activo.
- **Proceso**:
  - validación de campos obligatorios,
  - normalización de email/documento/teléfono,
  - asignación de empresa activa y usuario creador.
- **Output**: cliente creado, redirect a listado con mensaje de éxito.

### Edición Cliente

- **Input (POST)**: mismos campos.
- **Proceso**: validar cambios, conservar fecha_nac guardada si no se modifica, actualizar registro.
- **Output**: redirect con mensaje “Cliente actualizado”.

### Búsqueda Cliente

- **Input (GET)**: `q` (cadena).
- **Proceso**: selectors buscan en nombre, apellido, email, tel.
- **Output**: listado filtrado.

### Activar / Desactivar Cliente

- **Input (POST)**: acción sobre un cliente existente.
- **Proceso**: cambia flag `activo`.
- **Output**: redirect con mensaje de confirmación.

---

## 4) Dependencias e integraciones

- **Depende de `org`**: todos los clientes pertenecen a la empresa activa.
- **Integración futura con `vehicles`**: un cliente puede tener uno o varios vehículos.
- **Integración futura con `sales`**: las ventas requieren un cliente asociado.
- **Integración futura con `notifications`**: notificación de cumpleaños o segmentación por etiquetas.

---

## 5) Seguridad

- Todas las vistas requieren usuario autenticado.
- Validación multi-tenant:
  - Solo se listan/gestionan clientes de la empresa activa (`request.empresa_activa`).
- Acciones de activar/desactivar o eliminar restringidas a roles `admin` / `operador`.

---

## 6) Estado actual del módulo

- Modelo `Cliente` completo y migrado.
- `CustomerForm` con validaciones y normalización.
- Normalización de teléfono para Argentina → formato E.164 (+549…).
- Templates list, form, detail con `_form_fields.html` que muestran errores y mantienen valores (incluida fecha de nacimiento).
- Vistas CRUD + activar/desactivar implementadas.
- Admin: listado de clientes y filtros básicos.
- UX: mensajes de feedback (`django.contrib.messages`) integrados con Bootstrap.

---

## 7) Extensiones previstas

- Exportar/Importar clientes (CSV/Excel).
- Segmentación avanzada con `tags` o categorías predefinidas.
- Asociar clientes a vehículos (`apps.vehicles`).
- Mostrar historial de ventas en el `detail`.
- Hook de cumpleaños en `notifications`.
- Acciones masivas (activar/inactivar, exportar) en listado.

---

# Módulo 4 — `apps/vehicles` (Vehículos)

> **Objetivo del módulo:** Administrar los vehículos de los clientes, clasificarlos por tipo y mantenerlos disponibles para asociar a las ventas. Cada vehículo pertenece a un cliente y a una empresa (tenant).

---

## 1) Estructura de carpetas/archivos

```
apps/vehicles/
├─ __init__.py
├─ apps.py                   # Config de la app (name="apps.vehicles")
├─ admin.py                  # Registro de Vehículo y TipoVehículo en admin
├─ migrations/
│  └─ __init__.py
├─ models.py                 # Modelos: Vehiculo, TipoVehiculo
├─ urls.py                   # Rutas propias (listado, alta, edición, detalle)
├─ views.py                  # Vistas server-rendered CRUD de vehículos y tipos
├─ forms/
│  ├─ __init__.py
│  └─ vehicle.py             # Formularios de alta/edición de vehículo
├─ services/
│  ├─ __init__.py
│  ├─ vehicles.py            # Casos de uso: crear/editar vehículo
│  └─ types.py               # Casos de uso: CRUD de TipoVehiculo
├─ selectors.py              # Lecturas: buscar por patente, por cliente, listar tipos
├─ validators.py             # Validaciones específicas (ej. patente única por empresa)
├─ templates/
│  └─ vehicles/
│     ├─ list.html           # Listado de vehículos
│     ├─ form.html           # Alta/edición de vehículo
│     ├─ detail.html         # Detalle de vehículo
│     ├─ type_form.html      # Alta/edición de tipos
│     ├─ types_list.html     # Listado de tipos
│     └─ _form_fields.html   # Partial de formulario de vehículo
├─ static/
│  └─ vehicles/
│     ├─ vehicles.css        # Estilos propios (mínimos)
│     └─ vehicles.js         # Scripts UX (validaciones cliente-side, búsqueda rápida)
└─ emails/
   └─ vehicle_added.txt      # (Opcional) notificación al cliente al registrar vehículo
```

### Rol de cada componente

- **`models.py`**:
  - `TipoVehiculo`: catálogo de tipos de vehículos (auto, moto, camioneta, etc.).
  - `Vehiculo`: datos principales (cliente, tipo, marca, modelo, año, color, patente única por empresa, activo/inactivo).
- **`forms/vehicle.py`**: `VehicleForm` con validaciones y compatibilidad Bootstrap.
- **`services/vehicles.py`**: mutaciones de dominio (`crear_vehiculo`, `editar_vehiculo`, `activar_vehiculo`, `desactivar_vehiculo`).
- **`services/types.py`**: mutaciones de dominio sobre tipos de vehículo.
- **`selectors.py`**: consultas de lectura (`vehiculos_de(cliente)`, `buscar_por_patente`, `tipos_activos`).
- **`validators.py`**: helper de validación para patente única dentro de la empresa.
- **`views.py`**: CRUD con CBVs (`ListView`, `CreateView`, `UpdateView`, `DetailView`) tanto de vehículos como de tipos. Incluye mixin `BackUrlMixin` para soportar botón **Volver** en todas las vistas.
- **`templates/vehicles/*`**: interfaz UI con Bootstrap 5, hereda de `base_auth.html`.
  - `list.html`: tabla de vehículos con filtros.
  - `form.html`: alta/edición con `_form_fields.html`.
  - `detail.html`: ficha de vehículo.
  - `types_list.html` y `type_form.html`: gestión de tipos.
- **`static/vehicles/*`**: assets opcionales de mejora UX.

---

## 2) Endpoints implementados

- `/vehiculos/` → Listado de vehículos (con búsqueda y filtro por cliente).
- `/vehiculos/nuevo/` → Alta de vehículo (soporta `?cliente=<id>` para preseleccionar).
- `/vehiculos/<id>/editar/` → Edición de vehículo.
- `/vehiculos/<id>/detalle/` → Detalle de vehículo.
- `/vehiculos/<id>/activar/` → Reactivar vehículo.
- `/vehiculos/<id>/desactivar/` → Desactivar vehículo.
- `/vehiculos/tipos-vehiculo/` → Listado de tipos de vehículo.
- `/vehiculos/tipos-vehiculo/nuevo/` → Alta de tipo.
- `/vehiculos/tipos-vehiculo/<id>/editar/` → Edición de tipo.
- `/vehiculos/tipos-vehiculo/<id>/activar/` → Activar tipo.
- `/vehiculos/tipos-vehiculo/<id>/desactivar/` → Desactivar tipo.

---

## 3) Contratos de entrada/salida

### Alta Vehículo

- **Input (POST)**: cliente, tipo_vehiculo, marca, modelo, año, color, patente, notas, activo.
- **Proceso**:
  - Validación de unicidad de patente por empresa (en `validators.py`).
  - Persistencia vía `services.crear_vehiculo`.
  - Mensaje de éxito con `django.contrib.messages`.
- **Output**: redirect a:
  - `next` (si estaba en query/POST, p. ej. volver a edición de cliente),
  - o al listado de vehículos.

### Edición Vehículo

- **Input (POST)**: mismos campos.
- **Proceso**: validación de cambios, persistencia en `services.editar_vehiculo`.
- **Output**: redirect a `next` o al listado con mensaje de éxito.

### Activar/Desactivar Vehículo

- **Input (POST)**: ID de vehículo.
- **Proceso**: cambia flag `activo`.
- **Output**: redirect a `next` o listado.

### Alta/Edición TipoVehículo

- **Input (POST)**: nombre, slug, activo.
- **Proceso**: validación de slug único por empresa. Persistencia en `services/types.py`.
- **Output**: redirect a `next` (si existía, p. ej. volver a form de vehículo) o listado de tipos.

---

## 4) Dependencias e integraciones

- **Depende de `customers`**: cada vehículo requiere un cliente asociado.
- **Depende de `org`**: el vehículo y el tipo pertenecen a la empresa activa (`request.empresa_activa`).
- **Integración con `customers.detail.html`**: muestra todos los vehículos asociados a un cliente, con CTA “Agregar vehículo” si no tiene ninguno.
- **Integración futura con `sales`**: al crear una venta se seleccionará un vehículo de un cliente.
- **Integración futura con `pricing`**: el tipo de vehículo determina el precio base del servicio.

---

## 5) Seguridad

- Todas las vistas requieren usuario autenticado.
- Validación multi-tenant:
  - Solo se listan/gestionan vehículos de la empresa activa.
  - Las vistas de edición comprueban que el objeto pertenezca a la empresa activa.
- **Permisos declarados en `apps.org.permissions.Perm`:**
  - `VEHICLES_VIEW`, `VEHICLES_CREATE`, `VEHICLES_EDIT`, `VEHICLES_DEACTIVATE`, `VEHICLES_DELETE`
  - `VEHICLE_TYPES_VIEW`, `VEHICLE_TYPES_CREATE`, `VEHICLE_TYPES_EDIT`, `VEHICLE_TYPES_DEACTIVATE`, `VEHICLE_TYPES_DELETE`
- **Matriz de roles (`ROLE_POLICY`):**
  - **Admin**: todos los permisos de vehículos y tipos.
  - **Operador**: puede ver/crear/editar vehículos. Solo puede **ver** tipos de vehículo, sin crearlos ni editarlos.
- Control en backend con `EmpresaPermRequiredMixin` y `has_empresa_perm`. Los botones de UI se muestran/deshabilitan según los flags en contexto.

---

## 6) UX / UI

- Formularios con `crispy` Bootstrap manual (clases aplicadas en `_form_fields.html`).
- Botones **Volver** y **Cancelar**:
  - Implementados con `BackUrlMixin`.
  - Prioridad: `?next` > `HTTP_REFERER` > fallback (`list` o `types_list`).
- Listado de clientes muestra un resumen de sus vehículos (hasta 3 patentes, badge “+N” si hay más).
- Si el cliente no tiene vehículos → botón directo **Agregar vehículo** (lleva al form con `?cliente=<id>&next=<listado>`).
- En el form de vehículo, botón “+ Crear tipo” abre el alta de tipo con `next` apuntando al form actual → al guardar vuelve a la edición/alta del vehículo.
- En listados y formularios, los botones se muestran u ocultan según permisos calculados en `get_context_data`.

---

## 7) Estado actual

- Modelos y migraciones completas (`Vehiculo`, `TipoVehiculo`).
- Formularios con validaciones (patente única por empresa).
- Services y Selectors implementados (mutaciones y lecturas).
- CBVs CRUD funcionales, integradas con `BackUrlMixin` y `EmpresaPermRequiredMixin`.
- Templates `list`, `form`, `detail`, `types_list`, `type_form` listos y probados.
- Integración con `customers.detail.html` y `customers.list.html`.
- Sidebar actualizado: enlace directo a **Vehículos** en sección **Maestros**.

---

## 8) Extensiones previstas

- Exportar vehículos (CSV/Excel).
- Historial de lavados por vehículo (integración con `sales`).
- Notificación al cliente cuando el vehículo esté listo (`apps.notifications`).
- Filtros avanzados en listado (por tipo, año, color).
- Soporte para adjuntar fotos/documentos del vehículo.

---

## 9) Diagrama de relaciones

```mermaid
erDiagram
    Empresa ||--o{ Cliente : tiene
    Empresa ||--o{ TipoVehiculo : define
    Cliente ||--o{ Vehiculo : posee
    TipoVehiculo ||--o{ Vehiculo : clasifica

    Empresa {
        int id
        varchar nombre
    }

    Cliente {
        int id
        varchar nombre
        varchar apellido
        varchar email
        int empresa_id
    }

    TipoVehiculo {
        int id
        varchar nombre
        varchar slug
        bool activo
        int empresa_id
    }

    Vehiculo {
        int id
        varchar marca
        varchar modelo
        int anio
        varchar color
        varchar patente
        bool activo
        int cliente_id
        int tipo_id
        int empresa_id
    }
```

# Módulo 5 — `apps/catalog` (Catálogo de Servicios)

> **Objetivo del módulo:** Administrar el catálogo de **servicios** que ofrece el lavadero (lavado, encerado, interior, etc.), que luego serán asociados a precios y ventas. Este módulo es la fuente central de qué se puede vender.

---

## 1) Estructura de carpetas/archivos

```
apps/catalog/
├─ __init__.py
├─ apps.py                   # Config de la app (name="apps.catalog")
├─ admin.py                  # Registro de Servicio en admin
├─ migrations/
│  └─ __init__.py
├─ models.py                 # Modelo Servicio
├─ urls.py                   # Rutas propias (listado, alta, edición, detalle)
├─ views.py                  # Vistas server-rendered CRUD de servicios
├─ forms/
│  ├─ __init__.py
│  └─ service.py             # Formulario de alta/edición de servicio
├─ services/
│  ├─ __init__.py
│  └─ services.py            # Casos de uso: crear, editar, activar, desactivar, eliminar servicio
├─ selectors.py              # Lecturas: listar activos, buscar por nombre, get por ID
├─ templates/
│  └─ catalog/
│     ├─ list.html           # Listado de servicios
│     ├─ form.html           # Alta/edición
│     ├─ detail.html         # Detalle de servicio
│     └─ _form_fields.html   # Partial de formulario
├─ static/
│  └─ catalog/
│     ├─ catalog.css         # Estilos propios
│     └─ catalog.js          # Scripts UX
└─ emails/
   └─ service_updated.txt    # (Opcional) aviso interno si cambia un servicio
```

### Rol de cada componente

- **`models.py`**: define `Servicio` (nombre, descripción, slug, activo, timestamps, empresa FK).
- **`forms/service.py`**:
  - valida nombre único en empresa,
  - inyecta clases Bootstrap,
  - gestiona campo `activo` (oculto en creación, editable en edición).
- **`services/services.py`**: mutaciones de dominio (`crear_servicio`, `editar_servicio`, `activar_servicio`, `desactivar_servicio`, `eliminar_servicio`).
- **`selectors.py`**: consultas (`servicios_activos(empresa)`, `buscar_por_nombre`, `get_servicio_por_id`).
- **`views.py`**:
  - CBVs para List, Create, Update, Detail, Delete,
  - acciones POST para activar/desactivar,
  - soporte `?next` para redirecciones.
- **`templates/catalog/*`**: interfaz UI:
  - `list.html` listado con búsqueda, badges de estado, acciones,
  - `form.html` con `_form_fields.html`,
  - `detail.html` ficha completa con info, acciones y recordatorio de integraciones (pricing, sales).

---

## 2) Endpoints implementados

- `/catalogo/servicios/` → Listado de servicios (`ServiceListView`).
- `/catalogo/servicios/nuevo/` → Alta servicio (`ServiceCreateView`).
- `/catalogo/servicios/<id>/editar/` → Edición servicio (`ServiceUpdateView`).
- `/catalogo/servicios/<id>/detalle/` → Detalle de servicio (`ServiceDetailView`).
- `/catalogo/servicios/<id>/activar/` → Activar servicio (`ServiceActivateView`).
- `/catalogo/servicios/<id>/desactivar/` → Desactivar servicio (`ServiceDeactivateView`).
- `/catalogo/servicios/<id>/eliminar/` → Eliminar servicio (`ServiceDeleteView`).

---

## 3) Contratos de entrada/salida

### Alta Servicio

- **Input (POST)**: nombre, descripción opcional.
- **Proceso**:
  - validación de unicidad por empresa,
  - creación de `Servicio`,
  - asignación a empresa activa.
- **Output**: servicio creado, redirect a listado (o a `next` si existe), mensaje de éxito.

### Edición Servicio

- **Input (POST)**: nombre, descripción, activo.
- **Proceso**: validaciones y actualización.
- **Output**: redirect a listado (o `next`), mensaje “Servicio actualizado”.

### Detalle Servicio

- **Input (GET)**: id.
- **Proceso**: obtener servicio de empresa activa, validar permisos.
- **Output**: render `detail.html` con info completa y acciones.

### Listado Servicios

- **Input (GET)**: opcional `q` (búsqueda por nombre).
- **Proceso**: filtrar servicios de empresa activa, paginar.
- **Output**: render `list.html`.

### Activar/Desactivar Servicio

- **Input (POST)**: id + `csrf_token`.
- **Proceso**: cambiar flag `activo`.
- **Output**: redirect a listado o detalle (según `next`), mensaje confirmación.

### Eliminar Servicio

- **Input (POST)**: id + `csrf_token`.
- **Proceso**: borrado definitivo de `Servicio`.
- **Output**: redirect a listado (ignora `next` si apunta al detalle borrado), mensaje de confirmación.

---

## 4) Dependencias e integraciones

- **Depende de `org`**: cada servicio pertenece a la empresa activa.
- **Integración con `pricing`**: los precios se definen por combinación (`servicio` + `tipo_vehículo` + `sucursal`).
- **Integración con `sales`**: las ventas referencian un servicio del catálogo.
- **Integración UI**: sidebar actualizado con link directo a Catálogo de Servicios.

---

## 5) Seguridad

- Todas las vistas requieren usuario autenticado y empresa activa.
- Validación multi-tenant: solo se listan/gestionan servicios de la empresa activa (`request.empresa_activa`).
- **Permisos granulares (`apps.org.permissions.Perm`)**:
  - `CATALOG_VIEW`: ver/listar servicios (list/detail).
  - `CATALOG_CREATE`: crear servicios.
  - `CATALOG_EDIT`: editar servicios.
  - `CATALOG_ACTIVATE` / `CATALOG_DEACTIVATE`: cambiar estado activo.
  - `CATALOG_DELETE`: eliminar definitivamente.
- **Política por rol (`ROLE_POLICY`)**:
  - `admin`: todos los permisos sobre catálogo.
  - `operador`: solo `CATALOG_VIEW` (puede listar/ver detalle, no crear/editar).
  - `supervisor`: solo `CATALOG_VIEW` (lectura).
- Los botones en UI se muestran/ocultan o deshabilitan según flags de permisos (`puede_crear`, `puede_editar`, `puede_eliminar`, etc.).
- Backend aplica seguridad con `EmpresaPermRequiredMixin`, nunca solo en frontend.

---

## 6) Estado actual

- Modelo `Servicio` implementado con unicidad por empresa y slug autogenerado.
- Formularios estilizados con Bootstrap (`form-control`, `is-invalid`, `form-check-input`).
- Vistas CRUD, activación/desactivación y eliminación funcionando con permisos.
- Templates `list`, `form`, `detail` completos, con tooltips y modales de confirmación.
- Sidebar con link a “Catálogo de servicios”.
- Mensajes de éxito/error integrados con `django.contrib.messages`.

---

## 7) Extensiones previstas

- Exportar/Importar servicios (CSV/Excel).
- Historial de cambios en servicios (auditoría).
- Hooks de notificación (`service_updated.txt`).
- Integración más profunda con `pricing` para gestionar precios desde el detalle de servicio.
- Posibilidad de categorizar servicios por grupos (ej. básicos, premium).

---

## 8) Diagrama de relaciones (actual + integración futura con precios)

```mermaid
erDiagram
    Empresa ||--o{ Servicio : ofrece
    Servicio ||--o{ ServicePrice : tiene
    TipoVehiculo ||--o{ ServicePrice : condiciona
    Sucursal ||--o{ ServicePrice : aplica_en

    Empresa {
        int id
        varchar nombre
    }

    Servicio {
        int id
        varchar nombre
        text descripcion
        varchar slug
        bool activo
        int empresa_id
    }

    TipoVehiculo {
        int id
        varchar nombre
        bool activo
        int empresa_id
    }

    Sucursal {
        int id
        varchar nombre
        int empresa_id
    }

    ServicePrice {
        int id
        int servicio_id
        int tipo_vehiculo_id
        int sucursal_id
        decimal precio
        date vigente_desde
        date vigente_hasta
    }
```

# Módulo 6 — `apps/pricing` (Precios por Sucursal y Tipo de Vehículo)

> **Objetivo del módulo:** Definir y resolver el **precio vigente** de cada **Servicio × TipoVehículo × Sucursal** dentro de una Empresa. Es la fuente única de verdad para cálculos de ventas.

---

## 1) Estructura de carpetas/archivos

```
apps/pricing/
├─ __init__.py
├─ apps.py                    # Config de la app (name="apps.pricing")
├─ admin.py                   # Registro de modelos en admin
├─ migrations/
│  └─ __init__.py
├─ models.py                  # Modelo PrecioServicio (con vigencias)
├─ urls.py                    # Rutas propias (listado, alta, edición, desactivación)
├─ views.py                   # Vistas server-rendered CRUD y consulta
├─ forms/
│  ├─ __init__.py
│  └─ price.py                # Form de alta/edición (validaciones + widgets tipo date)
├─ services/
│  ├─ __init__.py
│  ├─ pricing.py              # Comandos: crear/actualizar precio; cerrar vigencias
│  └─ resolver.py             # Resolver: obtener precio vigente dado (srv, tipo, suc)
├─ selectors.py               # Lecturas: listar precios por filtros/estado
├─ validators.py              # Reglas: solapamiento de vigencias, consistencia de empresa, moneda válida
├─ templates/
│  └─ pricing/
│     ├─ list.html            # Listado con filtros, tabla responsive y acciones (editar/desactivar)
│     ├─ form.html            # Alta/edición de precio
│     └─ _form_fields.html    # Partial del formulario (Bootstrap)
└─ static/
   └─ pricing/
      ├─ pricing.css          # Estilos propios
      └─ pricing.js           # UX: filtros dinámicos, validaciones simples
```

### Rol de cada componente

- **`models.py`**: `PrecioServicio(empresa, sucursal, servicio, tipo_vehiculo, precio, moneda, vigencia_inicio, vigencia_fin, activo)`.
- **`forms/price.py`**:
  - valida montos y fechas,
  - fuerza `vigencia_inicio` y `vigencia_fin` como `<input type="date">` (calendario HTML5),
  - integra Bootstrap (`form-control`, `form-select`).
- **`validators.py`**: chequea **solapamientos** de vigencias y consistencia de pertenencia a empresa (sucursal, servicio, tipo).
- **`services/pricing.py`**: mutaciones seguras (cierre automático de vigencias previas, alta de nuevo precio, actualización).
- **`services/resolver.py`**: API interna para ventas: `get_precio_vigente(empresa, sucursal, servicio, tipo, fecha=None)`.
- **`selectors.py`**: consultas para listados y filtros (por sucursal, servicio, estado, fecha).
- **`templates/*`**: interfaz Bootstrap 5:
  - `list.html`: filtros amigables, tabla con botones de acción y modal de confirmación para desactivar,
  - `form.html` + `_form_fields.html`: alta/edición con selects dinámicos y calendarios.

---

## 2) Endpoints implementados

- `GET /precios/` → listado con filtros (sucursal, servicio, tipo, estado, vigencia).
- `GET /precios/nuevo/` → alta de precio.
- `POST /precios/nuevo/` → crear precio (cierra/ajusta vigencias previas si aplica).
- `GET /precios/<id>/editar/` → edición de precio.
- `POST /precios/<id>/editar/` → actualizar precio (opcional: finalizar vigencia).
- `POST /precios/<id>/desactivar/` → desactivar (soft-delete) y cerrar vigencia.

> Nota: el **resolver** de precios **no expone vista**; es consumido por `sales` vía `services.resolver`.

---

## 3) Contratos de entrada/salida

### Alta/Edición de Precio

- **Input (POST)**: `sucursal`, `servicio`, `tipo_vehiculo`, `precio`, `moneda`, `vigencia_inicio`, `vigencia_fin` (opcional).
- **Proceso**:
  - Validar que **no haya solapamiento** de vigencias para la misma combinación.
  - Validar consistencia: sucursal, servicio y tipo de vehículo deben pertenecer a la empresa activa.
  - Si existe un precio vigente que choca, **cerrar** su `vigencia_fin` al día anterior.
  - Persistir nuevo registro “activo”.
- **Output**: creación/actualización exitosa; redirect a `/precios/` con mensaje.

### Desactivación de Precio

- **Input (POST)**: id del precio a desactivar.
- **Proceso**: marcar como `activo=False` y, si corresponde, cerrar `vigencia_fin` con fecha de hoy.
- **Output**: redirect a `/precios/` con mensaje de éxito.

### Resolución de Precio (uso interno)

- **Input**: `empresa`, `sucursal`, `servicio`, `tipo_vehiculo`, `fecha` (default: hoy).
- **Proceso**: buscar registro con `vigencia_inicio <= fecha <= vigencia_fin (o NULL)` y `activo=True`, priorizando la fecha de inicio más reciente.
- **Output**: objeto `PrecioServicio` o excepción `PrecioNoDisponibleError`.

---

## 4) Dependencias e integraciones

- **Depende de `org`**: Sucursal y Empresa.
- **Depende de `catalog`**: Servicio.
- **Depende de `vehicles`**: TipoVehiculo.
- **Usado por `sales`**: cálculo de ítems en venta (precio unitario cacheado).

---

## 5) Seguridad

- **Tenancy:** todas las vistas filtran por `empresa=self.empresa` (provista por `TenancyMiddleware`).
- **Permisos granulares:** definidos en `apps.org.permissions.Perm` y asignados en `ROLE_POLICY`.
  - Admin: `PRICING_VIEW`, `PRICING_CREATE`, `PRICING_EDIT`, `PRICING_DEACTIVATE`, `PRICING_DELETE`.
  - Operador: solo `PRICING_VIEW`.
  - Supervisor (opcional): solo `PRICING_VIEW`.
- **Enforcement backend:** las vistas usan `EmpresaPermRequiredMixin` + `required_perms`.
  - List: `(Perm.PRICING_VIEW,)`
  - Create: `(Perm.PRICING_CREATE,)`
  - Edit: `(Perm.PRICING_EDIT,)`
  - Deactivate: `(Perm.PRICING_DEACTIVATE,)`
- **UI/UX:** flags `puede_crear`, `puede_editar`, `puede_eliminar`, `puede_desactivar` para mostrar/ocultar botones.
  - La acción de desactivar se confirma con un **modal Bootstrap**, no con alert JS.
- **Validaciones:** `validators.py` asegura consistencia de empresa y no solapamiento de vigencias.

---

## 6) Estado actual del módulo

- Modelo `PrecioServicio` migrado y en uso.
- Formularios con selects dinámicos y `<input type="date">` para vigencias.
- Validaciones de solapamiento y de pertenencia a empresa activa funcionando.
- Vistas CRUD limpias con CBVs y permisos granulares.
- Vista de desactivación implementada como soft-delete con confirmación modal.
- Redirecciones controladas (`?next`) para mejor UX.
- Templates Bootstrap 5: UX consistente con sidebar y otros módulos.
- Admin: registro de `PrecioServicio` con filtros por empresa, servicio, sucursal y vigencia.

---

## 7) Roadmap próximo

1. Mejorar filtros en `list.html` con selects dependientes (sucursal → servicios de esa sucursal).
2. Integrar el resolver directamente en `sales` para precargar precio unitario en línea de venta.
3. Exportar precios (CSV/Excel) con filtros aplicados.
4. Agregar historial de cambios (auditoría).
5. Integración de notificaciones cuando se actualicen precios.
6. Evaluar si corresponde implementar eliminación definitiva (hard delete) o mantener siempre soft-delete.

---

## 8) Diagrama de relaciones

```mermaid
erDiagram
    Empresa ||--o{ Sucursal : contiene
    Empresa ||--o{ Servicio : ofrece
    Empresa ||--o{ TipoVehiculo : define
    Sucursal ||--o{ PrecioServicio : tiene
    Servicio ||--o{ PrecioServicio : tiene
    TipoVehiculo ||--o{ PrecioServicio : condiciona

    Empresa {
        int id
        varchar nombre
    }

    Sucursal {
        int id
        varchar nombre
        int empresa_id
    }

    Servicio {
        int id
        varchar nombre
        text descripcion
        int empresa_id
    }

    TipoVehiculo {
        int id
        varchar nombre
        int empresa_id
    }

    PrecioServicio {
        int id
        int sucursal_id
        int servicio_id
        int tipo_vehiculo_id
        decimal precio
        varchar moneda
        date vigencia_inicio
        date vigencia_fin
        bool activo
        int empresa_id
    }
```

# Módulo 7 — `apps/sales` — Ventas / Órdenes de Servicio

Sistema de gestión de **ventas** (órdenes de servicio) para lavaderos. Cubre: alta y edición de ventas, manejo de **ítems** (servicios), **estados de proceso (FSM)**, **pagos**, **comprobantes**, **notificaciones** y un módulo completo de **promociones/descuentos** con control de permisos.

---

## 1) Propósito y alcance

- **Entidad principal:** `Venta` (orden de servicio) que orquesta ítems, totales, pagos, emisión de comprobantes y notificaciones.
- **Experiencia operativa:** flujo claro desde el **borrador** hasta el **terminado/pagado**, con reglas que impiden errores comunes (editar ítems en estados finales, facturar si no está pagada, etc.).
- **Multi-empresa / multi-sucursal:** toda la lógica respeta empresa activa y sucursal activa.
- **Seguridad por roles:** capacidades diferenciadas para **Administrador** y **Operador** (ver §6).

---

## 2) Mapa del módulo (qué es cada cosa)

Estructura lógica (archivos y carpetas) y su razón de ser. No se incluyen fragmentos de código aquí: el objetivo es entender **qué hace** cada pieza.

```
apps/sales/
├─ admin.py                # Alta en Django Admin: Venta, VentaItem, Promotion, SalesAdjustment
├─ apps.py                 # Configuración de la app
├─ calculations.py         # Motor de totales (subtotal, descuentos, propina, total, saldo)
├─ fsm.py                  # Máquina de estados de la Venta (reglas de transición)
├─ models.py               # Modelos: Venta, VentaItem, Promotion, SalesAdjustment
├─ selectors.py            # (Opcional) Lecturas optimizadas y consultas de apoyo
├─ services/
│  ├─ sales.py             # Orquestación de ventas: crear, iniciar/finalizar, cancelar, recalcular
│  ├─ items.py             # Operaciones con ítems: agregar/quitar/actualizar y recalcular
│  ├─ lifecycle.py         # Hooks de negocio: on_iniciar, on_finalizar, on_pagada, on_cancelar
│  └─ discounts.py         # Negocio de promociones y descuentos (aplicar/quitar, vigencia, unicidad)
├─ forms/
│  ├─ sale.py              # VentaForm (cliente, vehículo, notas)
│  ├─ service_select.py    # ServiceSelectionForm (servicios con precio vigente)
│  ├─ discounts.py         # Formularios de ajustes: venta/ítem y aplicar promoción
│  └─ promotion.py         # Formulario de gestión de promociones (admin)
├─ templates/sales/
│  ├─ list.html            # Listado con filtros y acciones rápidas
│  ├─ create.html          # Alta guiada en dos pasos (cliente/vehículo → servicios)
│  ├─ detail.html          # Detalle integral de la venta
│  ├─ _summary_card.html   # Resumen de montos (subtotal, descuento, propina, total, saldo)
│  ├─ _discounts_card.html # Tabla de ajustes + modales (promos/desc.)
│  ├─ _item_row.html       # Fila reutilizable de ítem en la tabla
│  ├─ _services_add_card.html # Panel lateral para agregar servicios
│  ├─ _payments_card.html  # Pagos asociados y CTA para registrar
│  └─ _messages.html       # Mensajes flash coherentes
├─ urls.py                 # Enrutamiento público del módulo
├─ views.py                # Vistas de ventas (listado, alta, detalle, acciones de estado)
└─ views_promotions.py     # Vistas de promociones/ajustes (gestión y aplicación a ventas)
```

**Reglas de diseño clave**

- **Servicios** encapsulan la lógica de negocio; las **vistas** coordinan entrada/salida y contextos; los **templates** renderizan sin lógica compleja (reciben _flags_).
- **FSM** y **calculation engine** están separados para ser testeables y reusables.
- **Promos/descuentos** viven en su propio _service_ con validaciones estrictas e integridad en DB.

---

## 3) Data Model — visión conceptual

No se muestran campos específicos; esto es una vista funcional con las relaciones relevantes.

```mermaid
erDiagram
    Empresa ||--o{ Sucursal : tiene
    Empresa ||--o{ Cliente  : tiene
    Cliente ||--o{ Vehiculo : posee

    Empresa ||--o{ Promotion       : define
    Sucursal ||--o{ Promotion      : "restringe a sucursal (opcional)"

    Sucursal ||--o{ Venta          : opera
    Cliente  ||--o{ Venta          : solicita
    Vehiculo ||--o{ Venta          : se_atiende_en

    Venta ||--o{ VentaItem         : compone
    VentaItem }o--|| Servicio      : referencia
    Venta ||--o{ SalesAdjustment   : ajusta_total
    VentaItem ||--o{ SalesAdjustment : ajusta_subtotal
    Promotion ||--o{ SalesAdjustment : aplica_promocion

    %% Extras fuera del módulo (no definidas aquí)
    Venta ||..|| Comprobante : emite
    Venta ||..o{ Pago        : registra
```

**Significado práctico**

- `Venta` es la entidad madre: su **estado**, **totales** y **relaciones** determinan qué acciones son válidas.
- `Promotion` describe reglas de descuento parametrizadas; `SalesAdjustment` es la **aplicación** concreta a una venta o a un ítem.
- `VentaItem` cachea precio/condiciones al momento del agregado (para trazabilidad).

---

## 4) Máquina de estados (FSM) de la Venta

Flujo operativo de trabajo (independiente del pago).

```mermaid
stateDiagram-v2
    [*] --> borrador
    borrador --> en_proceso: iniciar_trabajo
    en_proceso --> terminado: finalizar_trabajo

    %% Pagos pueden cerrar en pagado cuando saldo=0
    borrador --> pagado: saldo_pendiente=0
    en_proceso --> pagado: saldo_pendiente=0
    terminado --> pagado: saldo_pendiente=0

    %% Cancelación (regla de negocio) antes de estados finales
    borrador --> cancelado: cancelar
    en_proceso --> cancelado: cancelar
    terminado --> cancelado: cancelar

    pagado --> [*]
    cancelado --> [*]
```

**Políticas asociadas**

- **Edición de ítems y ajustes** permitida en `borrador` y `en_proceso`; **bloqueada** desde `terminado`.
- **Comprobante** solo cuando la venta está **pagada** (independiente del proceso).
- **Notificaciones** al cliente cuando la venta está **terminada** (pago puede ser antes o después).
- El cambio de estado respeta reglas de **`fsm.py`** y se canaliza por **servicios**.

---

## 5) Totales: cómo se calculan

Pipeline conceptual de cómputo de montos.

```mermaid
flowchart TD
    A[Items de Venta] --> B[Subtotal Items]
    B --> C[SalesAdjustments por Ítem]
    C --> D[Subtotal Ajustado de Ítems]
    D --> E[SalesAdjustments por Venta]
    E --> F[Subtotal Final con Descuentos]
    F --> G[Propina]
    G --> H[Total]
    H --> I[Pagos registrados]
    I --> J[Saldo pendiente]
```

**Puntos a entender**

- Los **ajustes** pueden ser **por ítem** o **por venta**; cada uno aplica en su etapa correspondiente.
- Un ajuste puede ser **porcentaje** o **monto**; la lógica y validación viven en `services/discounts.py`.
- **Recalcular** sucede automáticamente tras mutaciones (agregar/quitar ítems, aplicar/quitar ajustes, registrar pagos).

---

## 6) Roles y permisos (quién puede hacer qué)

El módulo no decide roles, sino que **consume** permisos desde `apps.org.permissions`. La matriz operativa es:

```mermaid
classDiagram
    class Permisos {
      SALES_VIEW
      SALES_CREATE
      SALES_EDIT
      SALES_FINALIZE
      SALES_CANCEL
      SALES_ITEM_ADD
      SALES_ITEM_UPDATE_QTY
      SALES_ITEM_REMOVE

      SALES_PROMO_MANAGE     %% admin: gestionar promociones
      SALES_PROMO_APPLY      %% admin + operador: aplicar a ventas
      SALES_DISCOUNT_ADD     %% admin: desc. manuales
      SALES_DISCOUNT_REMOVE  %% admin: quitar cualquier ajuste
    }

    class Admin {
      +ver ventas
      +crear/editar ventas
      +gestionar ítems
      +transiciones (iniciar/finalizar/cancelar)
      +gestionar promociones (CRUD/activar)
      +aplicar promociones
      +aplicar descuentos manuales
      +eliminar ajustes
    }

    class Operador {
      +ver ventas
      +crear/editar ventas
      +gestionar ítems
      +transiciones (según política)
      +aplicar promociones
      -gestionar promociones (no)
      -descuentos manuales (no)
      -eliminar ajustes (no)
    }

    Permisos <.. Admin
    Permisos <.. Operador
```

**Defensa en profundidad**

- Los **templates** muestran/ocultan CTAs según flags de permiso.
- Las **vistas** validan permisos requeridos.
- Los **servicios** vuelven a validar permisos críticos (p. ej., descuentos manuales).

---

## 7) Flujos UI principales

### 7.1 Crear Venta (2 pasos)

1. GET: seleccionar **Cliente** → habilita **Vehículo** (solo del cliente).
2. POST: checkboxes de **Servicios** disponibles (filtrados por sucursal/tipo de vehículo/precio vigente).

```mermaid
sequenceDiagram
    participant U as Usuario
    participant V as Vista Create
    participant S as Service (sales)
    U->>V: GET /ventas/nueva/
    V-->>U: Form Cliente + Vehículo (auto-submit)
    U->>V: GET con cliente seleccionado
    V-->>U: Vehículos del cliente + Servicios disponibles
    U->>V: POST (cliente, vehiculo, servicios, notas)
    V->>S: crear_venta + agregar_items
    S-->>V: OK (venta en borrador)
    V-->>U: Redirect a Detail
```

### 7.2 Detalle de Venta

- **Secciones:** Meta (cliente/vehículo/sucursal/fechas), **Ítems**, **Resumen**, **Comprobante**, **Notificaciones**, **Descuentos y promociones**.
- **Acciones rápidas** según estado/permiso: iniciar, finalizar, cancelar; agregar/quitar ítems; aplicar promos; descuentos manuales (solo admin).

### 7.3 Aplicar Promoción

```mermaid
sequenceDiagram
    participant U as Usuario (Admin u Operador)
    participant D as View Detail
    participant P as View PromotionApply
    participant S as Service discounts
    U->>D: Abrir modal Promo (venta o ítem)
    U->>P: POST promotion_id [+ item_id]
    P->>S: aplicar_promocion(...)
    S-->>P: Ajuste creado + recalcular totales
    P-->>U: Mensaje éxito + redirect a Detail
```

### 7.4 Descuento Manual (solo Admin)

Igual a la promo, pero con formularios de modo/valor/motivo y validación de permisos más estricta (no visible ni permitido al operador).

---

## 8) Rutas (enrutamiento público)

> Prefijo típico en `urls.py` del proyecto: `path("ventas/", include(("apps.sales.urls", "sales"), namespace="sales"))`

**Ventas**

- `GET /ventas/` — listado, con filtros por estado/pago/sucursal, acciones rápidas por fila.
- `GET|POST /ventas/nueva/` — flujo de alta (cliente/vehículo/servicios).
- `GET /ventas/<uuid:pk>/` — detalle integral.
- `POST /ventas/<uuid:pk>/iniciar/` — iniciar trabajo.
- `POST /ventas/<uuid:pk>/finalizar/` — finalizar trabajo.
- `POST /ventas/<uuid:pk>/cancelar/` — cancelar venta.
- `POST /ventas/<uuid:pk>/items/agregar/` — agregar servicio.
- `POST /ventas/<uuid:pk>/items/<int:item_id>/eliminar/` — quitar servicio.

**Promos/Ajustes sobre ventas**

- `POST /ventas/<uuid:pk>/promos/aplicar/` — aplicar promoción (admin + operador).
- `POST /ventas/<uuid:pk>/descuentos/agregar/venta/` — descuento manual (solo admin).
- `POST /ventas/<uuid:pk>/descuentos/agregar/item/` — descuento manual por ítem (solo admin).
- `POST /ventas/<uuid:pk>/descuentos/<int:adj_id>/eliminar/` — quitar ajuste (solo admin).

**Gestión de Promos (solo Admin)**

- `GET /ventas/promos/` — listado de promociones.
- `GET|POST /ventas/promos/nueva/` — crear.
- `GET|POST /ventas/promos/<int:pk>/editar/` — editar.
- `POST /ventas/promos/<int:pk>/eliminar/` — eliminar.
- `POST /ventas/promos/<int:pk>/toggle/` — activar/desactivar.

---

## 9) Integraciones y dependencias externas

- **Pricing**: resolución de precios vigentes por sucursal y tipo de vehículo. El selector de servicios **solo** ofrece lo que tiene precio vigente.
- **Payments**: registra pagos y recalcula saldo; si el saldo llega a 0 y la venta no está cancelada, el ciclo normal marca **pagado**.
- **Invoicing**: emisión de comprobantes únicamente si la venta está **pagada**; puede ser **auto** desde un hook si está habilitado.
- **Notifications**: envío por WhatsApp cuando la venta está **terminada** y existen plantillas activas.

---

## 10) Seguridad y Tenancy

- Todas las vistas usan el **mixin de empresa** y filtran por **empresa activa**.
- **Sucursal activa** proviene del middleware y limita precios/promos/servicios a mostrar/aplicar.
- **Permisos** se evalúan en **tres capas**:
  1. **Templates**: ocultan/inhabilitan CTAs (usabilidad).
  2. **Vistas**: bloquean acceso (seguridad).
  3. **Servicios**: vuelven a validar (defensa en profundidad).

---

## 11) Promociones y Descuentos — reglas de negocio

- **Vigencia**: promo activa y dentro de su ventana (`valido_desde`/`valido_hasta`).
- **Scope**: `venta` o `ítem`. Si es por ítem, exige target explícito.
- **Unicidad**: la **misma** promoción no puede aplicarse dos veces al **mismo** target; lo garantiza la base con constraints.
- **Stacking**: por defecto se permite acumular (configurable por `stackable`, prioridad y reglas futuras).
- **Permisos**:
  - **Aplicar promoción**: Admin y Operador.
  - **Descuento manual** y **Eliminar ajustes**: solo Admin.
  - **Gestionar promociones** (CRUD/activar): solo Admin.
- **Estados**: ajustes solo en `borrador` / `en_proceso` (bloqueo en `terminado`/`cancelado`).

---

## 12) Performance y calidad

- **Querysets** en vistas: `select_related` / `prefetch_related` donde corresponde (cliente, vehículo, ítems, ajustes, pagos).
- **Plantillas** simples con fragmentos parciales reutilizables.
- **Recalcular** solo tras cambios; operaciones idempotentes donde es razonable.
- **Mensajería** coherente: todas las acciones informan éxito/error en la UI.

---

## 13) Testing recomendado (enfoque)

- **Unit**:
  - `fsm`: transiciones válidas e inválidas.
  - `calculations`: totales ante combinaciones de ítems y ajustes.
  - `discounts`: vigencia, unicidad, permisos, aplicar/eliminar y side-effects (recalcular).
- **Integration**:
  - Flujos UI (crear → detalle → aplicar promo → finalizar → pagar → emitir).
  - Permisos (operador vs admin) en vistas y services.
- **E2E feliz y con errores**:
  - Promo duplicada → error legible.
  - Descuento manual por operador → prohibido.
  - Editar ítems en terminado → bloqueado.

---

## 14) Operación diaria (guía breve)

- **Operador**:
  1. Crea venta (selecciona cliente/vehículo) y agrega servicios.
  2. Aplica **promociones** vigentes (si hay).
  3. Inicia/finaliza el trabajo.
  4. Registra pagos del cliente.
  5. Cuando el saldo sea 0, la venta queda **pagada**; si corresponde, emissão del comprobante.
- **Admin**:
  - Configura **promociones** (empresa/sucursal, vigencia, modo, valor, prioridad, stacking).
  - Puede aplicar **descuentos manuales** (casos excepcionales) y **eliminar ajustes**.
  - Supervisa cierre de ventas, emisión y reportes.

---

## 15) Glosario mínimo

- **Venta**: orden de servicio; unidad de trabajo sobre un vehículo para un cliente.
- **Ítem**: servicio prestado dentro de la venta.
- **Ajuste**: modificación del subtotal (por ítem o por venta), originada por **promoción**, **descuento manual** o **método de pago**.
- **Promoción**: regla parametrizable (vigencia, modo, valor, alcance) que genera ajustes al aplicarse.
- **Saldo**: total menos pagos aplicados; si llega a 0 → **pagada**.
- **Terminado**: estado operativo que indica que el trabajo finalizó (independiente del pago).

---

## 16) Diagramas de referencia

### 16.1 Arquitectura lógica (capas)

```mermaid
graph TD
    UI[Templates] --> V[Views]
    V --> S1[services.sales]
    V --> S2[services.items]
    V --> S3[services.discounts]
    S1 --> M[Models]
    S2 --> M
    S3 --> M
    V --> FSM[fsm]
    V --> CALC[calculations]
    V --> EXT[(Pricing/Payments\nInvoicing/Notifications)]
```

### 16.2 Secuencia aplicar descuento/promoción

```mermaid
sequenceDiagram
    participant U as Usuario
    participant VW as Vista Venta (Detail)
    participant VP as Vista Acción (Promo/Desc)
    participant SD as services.discounts
    participant CALC as calculations

    U->>VW: Abrir modal
    U->>VP: POST (datos)
    VP->>SD: Validar permisos/estado/vigencia/unicidad
    SD->>M: Crear ajuste
    SD->>CALC: Recalcular totales
    CALC-->>SD: Totales actualizados
    SD-->>VP: OK
    VP-->>U: Mensaje + redirect
```

### 16.3 Matriz de edición por estado

```mermaid
classDiagram
    class Borrador {
      +Editar ítems: Sí
      +Aplicar promos: Sí
      +Desc. manuales: Sí (Admin)
      +Eliminar ajustes: Sí (Admin)
    }
    class EnProceso {
      +Editar ítems: Sí
      +Aplicar promos: Sí
      +Desc. manuales: Sí (Admin)
      +Eliminar ajustes: Sí (Admin)
    }
    class Terminado {
      +Editar ítems: No
      +Aplicar promos: No
      +Desc. manuales: No
      +Eliminar ajustes: No
    }
    class Cancelado {
      +Acciones: No
    }
```

---

## 17) Buenas prácticas operativas

- Mantener **precios** por sucursal y tipo de vehículo al día para que el selector ofrezca solo servicios vigentes.
- Usar **promociones** para políticas comerciales recurrentes y **descuentos manuales** solo como excepción (admin).
- Revisar **mensajería** de error/éxito para asegurar visibilidad de las acciones a los usuarios.
- Monitorear el **listado de ventas** con filtros para trabajo en curso (en proceso) y pendientes de notificación o pago.

---

# Módulo 8 — `apps/payments` (Pagos)

> **Objetivo del módulo:** Registrar **pagos** para una venta (medio, monto, propina), mantener **saldo** consistente y, cuando el saldo llegue a **0**, pasar la venta a **`pagado`** (aunque esté en `borrador`/`en_proceso`). El módulo garantiza **idempotencia** básica, maneja **sobrepago** con confirmación (puede **dividir** en pago + propina) y aporta trazabilidad (`referencia`, `idempotency_key`).  
> **Stack:** Django + CBVs server-rendered, Bootstrap 5 (modales; sin `confirm()` nativo).

---

## 1) Estructura de carpetas/archivos (actualizada)

```
apps/payments/
├─ __init__.py
├─ apps.py                       # name="apps.payments"
├─ admin.py                      # Registro de MedioPago y Pago
├─ migrations/
│  └─ __init__.py
├─ models.py                     # MedioPago, Pago
├─ urls.py                       # Rutas (crear pago, confirmar sobrepago, listado; CRUD de medios)
├─ views.py                      # Vistas de pagos (form de pago + sobrepago integrado + list)
├─ views_medios.py               # Vistas de gestión de medios de pago (list/create/update/toggle)
├─ forms/
│  ├─ __init__.py
│  ├─ payment.py                 # PaymentForm (medio, monto, es_propina, referencia, idempotency_key, notas)
│  └─ medio_pago.py              # MedioPagoForm (nombre, activo) con validaciones por empresa
├─ services/
│  ├─ __init__.py
│  └─ payments.py                # registrar_pago(), recalcular_saldo(), OverpayNeedsConfirmation
├─ selectors.py                  # Consultas (pagos por venta, por rango/medio/sucursal)
├─ validators.py                 # (Opcional) Reglas extra; parte quedó en services/models
├─ templates/
│  └─ payments/
│     ├─ form.html               # Alta de pago (desde detalle de venta), modal de sobrepago
│     ├─ list.html               # (Opcional) Listado global/por fecha
│     ├─ medios_list.html        # Gestión de medios (admin)
│     ├─ medios_form.html        # Nuevo/Editar medio (admin)
│     └─ _summary_sale.html      # (Opcional) Resumen venta+saldo para sidebar
└─ static/
   └─ payments/
      ├─ payments.js             # (Opcional) UX (máscaras, autoselect)
      └─ payments.css            # (Opcional) Estilos
```

**Cambios clave vs. borrador anterior**

- **Permisos granulares por rol** integrados con la infraestructura común (`apps.org.permissions`).
  - Nuevos **Perm**: `PAYMENTS_VIEW`, `PAYMENTS_CREATE`, `PAYMENTS_EDIT`, `PAYMENTS_DELETE`, `PAYMENTS_CONFIG`.
  - Mapeo en `ROLE_POLICY`: **admin** acceso total; **operador** crear/ver; **supervisor** ver.
- Todas las CBVs usan **`EmpresaPermRequiredMixin`** (no `LoginRequiredMixin` directo) y **Tenancy** desde `EmpresaContextMixin`.
  - Las vistas definen `required_perms = (Perm.XXX,)` y **filtran por `self.empresa_activa`**.
- **Flags de UI** en contextos: `puede_crear`, `puede_configurar`, etc. para habilitar/ocultar CTAs en templates — **sin lógica de seguridad en front**.
- Se incorporó **gestión de medios de pago** por empresa (`MedioPago`), con **CRUD** protegido por `PAYMENTS_CONFIG`.

---

## 2) Endpoints

```
# Pagos
GET  /ventas/<uuid:venta_id>/pagos/nuevo/                name="payments:create"
POST /ventas/<uuid:venta_id>/pagos/nuevo/                name="payments:create"
GET  /pagos/                                             name="payments:list"       # opcional

# Medios de pago (configuración admin)
GET  /pagos/medios/                                      name="payments:medios_list"
GET  /pagos/medios/nuevo/                                name="payments:medios_create"
POST /pagos/medios/nuevo/                                name="payments:medios_create"
GET  /pagos/medios/<int:pk>/editar/                      name="payments:medios_update"
POST /pagos/medios/<int:pk>/editar/                      name="payments:medios_update"
POST /pagos/medios/<int:pk>/toggle/                      name="payments:medios_toggle"
```

> Entrada típica: botón **“Registrar pago”** en `sales:detail` abre `payments:create` (misma página o ruta dedicada).

---

## 3) Modelos

### 3.1 `MedioPago`

- Campos: `empresa(FK)`, `nombre`, `activo`, timestamps.
- Constraint: **único** por `empresa+nombre` (evita duplicados: “Efectivo”, “Transferencia BBVA”, etc.).

### 3.2 `Pago`

- Campos: `id(UUID pk)`, `venta(FK)`, `medio(FK)`, `monto(>0)`, `es_propina(bool)`, `referencia`, `notas`, `idempotency_key`, `creado_por(FK user)`, timestamps.
- Índices: por fecha y `(venta, es_propina)`.
- Constraint: `monto > 0`. Idempotencia condicional por `(venta, idempotency_key)` (cuando la key no es `NULL`).

**Reglas de negocio**

- **Propina** no descuenta saldo.
- **Idempotencia**: si existe `(venta, idempotency_key)`, se retorna ese pago y se recalcula saldo (no duplica).
- **Sobrepago**:
  - Si el pago NO es propina y `monto > saldo` → se exige confirmación para registrar **diferencia como propina**.
  - Al confirmar (o con `auto_split_propina=True`), se crean **dos pagos** con keys derivadas: `"<key>:saldo"` y `"<key>:propina"`.

---

## 4) Services

### 4.1 `registrar_pago(venta, medio, monto, es_propina, referencia, notas, creado_por, idempotency_key=None, auto_split_propina=False) -> list[Pago]`

- Bloquea la venta con `select_for_update()` (consistencia en concurrencia).
- Valida `monto > 0` y `medio.empresa == venta.empresa` (tenancy).
- Idempotencia simple (cuando **no hay split**).
- Recalcula saldo **antes y después**; si queda en 0 y venta no está “cancelado” → `sales.services.marcar_pagada(venta)`.
- Casuística:
  - `es_propina=True` → crea pago propina, recalcula.
  - `es_propina=False` y `monto <= saldo` → crea pago normal, recalcula.
  - `es_propina=False` y `monto > saldo` → `OverpayNeedsConfirmation` o split automático (saldo + propina).

### 4.2 `recalcular_saldo(venta)`

- Suma pagos **no propina** y setea `venta.saldo_pendiente = max(venta.total - sum, 0)` (update atómico).
- **No** toca FSM; la transición a “pagado” se hace en `_post_recalculo_y_pagado()` del service.

> **Nota operativa:** una venta puede quedar **`pagado`** aun en `borrador` o `en_proceso`. Luego puede marcarse `terminado` para notificar.

---

## 5) Permisos y roles (integración con `apps.org.permissions`)

### 5.1 Enumeración de permisos (`Perm`)

```text
PAYMENTS_VIEW     # ver pagos (listados / lectura)
PAYMENTS_CREATE   # registrar pago
PAYMENTS_EDIT     # editar pago (si se habilita en roadmap)
PAYMENTS_DELETE   # eliminar/revertir pago (si se habilita)
PAYMENTS_CONFIG   # gestionar medios de pago (CRUD + activar/desactivar)
```

### 5.2 Política por rol (`ROLE_POLICY`)

- **admin**: `PAYMENTS_VIEW`, `PAYMENTS_CREATE`, `PAYMENTS_EDIT`, `PAYMENTS_DELETE`, `PAYMENTS_CONFIG`
- **operador**: `PAYMENTS_VIEW`, `PAYMENTS_CREATE`
- **supervisor**: `PAYMENTS_VIEW`

> **Fuente de verdad**: `apps.org.permissions.Perm` + `ROLE_POLICY`. **No se consultan roles directos** (`EmpresaMembership.rol`) en vistas/plantillas.

```mermaid
classDiagram
  class Perm {
    +PAYMENTS_VIEW
    +PAYMENTS_CREATE
    +PAYMENTS_EDIT
    +PAYMENTS_DELETE
    +PAYMENTS_CONFIG
  }
  class Admin {
    +ver/crear/editar/borrar pagos
    +configurar medios
  }
  class Operador {
    +ver/crear pagos
    -editar/borrar
    -configurar medios
  }
  class Supervisor {
    +ver
  }
  Perm <.. Admin
  Perm <.. Operador
  Perm <.. Supervisor
```

---

## 6) Vistas y seguridad declarativa (CBVs)

### 6.1 Patrón de uso

- Todas las vistas heredan de **`EmpresaPermRequiredMixin`** (que ya incluye `LoginRequiredMixin` + contexto de empresa).
- Cada vista declara `required_perms = (Perm.XXX,)` y **filtra** por `self.empresa_activa` en `get_queryset()` / `get_object()`.

**Helpers disponibles**

- `has_empresa_perm(user, empresa, perm)` para **flags de UI** (no para seguridad).
- **No** crear helpers alternativos tipo `membership.has_perm` ni mezclar `LoginRequiredMixin` con `EmpresaPermRequiredMixin`.

### 6.2 Vistas de pagos (`apps/payments/views.py`)

- `PaymentCreateView`

  - `required_perms = (Perm.PAYMENTS_CREATE,)`
  - Flags en contexto: `puede_crear`, `puede_configurar` (para botones/avisos).
  - Rechaza pagos sobre ventas `cancelado`.
  - Defensa multi-tenant extra: `medio.empresa_id == venta.empresa_id`.
  - Sobrepago: `OverpayNeedsConfirmation` → render con aviso y `<input hidden name="confirmar_split" value="1">` al confirmar.

- `PaymentListView` (opcional)
  - `required_perms = (Perm.PAYMENTS_VIEW,)`
  - Queryset filtrado por `venta__empresa=self.empresa_activa`.
  - Flags en contexto: `puede_crear`, `puede_configurar`.

### 6.3 Vistas de medios (`apps/payments/views_medios.py`)

- `MedioPagoListView`, `MedioPagoCreateView`, `MedioPagoUpdateView`, `MedioPagoToggleActivoView`
  - `required_perms = (Perm.PAYMENTS_CONFIG,)`
  - Tenancy estricto: `empresa=self.empresa_activa` en queryset/objeto.
  - Mixin auxiliar interno **`_PermCtxMixin`** inyecta `puede_configurar` en el contexto para **todas** estas vistas.

---

## 7) Templates (flags y UX)

### 7.1 `payments/form.html` (registrar pago)

- Muestra aviso si `requiere_confirmacion` (fallback servidor).
- **Flags**:
  - `puede_crear` → habilita botón “Registrar pago” o “Confirmar y aplicar diferencia…”.
  - `puede_configurar` → botón “Configurar medios”.
- Modal Bootstrap de sobrepago (JS) para confirmar el split **antes** del submit.

### 7.2 `payments/list.html` (listado de pagos)

- **Flags**:
  - `puede_crear` → CTA “Registrar pago” (opcional).
  - `puede_configurar` → CTA “Configurar medios”.
- Tabla con: fecha, venta, método, monto, propina, usuario, referencia.

### 7.3 `payments/medios_list.html`

- **Flag** `puede_configurar`: muestra/oculta “Nuevo medio”, “Editar” y “Activar/Desactivar”.
- Confirmación simple en toggle con `onsubmit="return confirm(...)"`.

### 7.4 `payments/medios_form.html`

- **Flag** `puede_configurar`: aviso si no tiene permiso y deshabilita el botón **(defensa visual; el mixin ya bloquea)**.

### 7.5 `_summary_sale.html`

- Solo lectura (cliente/vehículo/total/saldo). **No requiere flags**, salvo que se decida agregar CTAs.

> **Importante**: los templates **no implementan la seguridad**; solo mejoran la UX. La seguridad está en **mixins** y **services**.

---

## 8) Integración con `sales` e `invoicing`

- `sales:detail` incluye **tabla de pagos** y botón “Registrar pago” si `puede_crear`.
- El service recalcula **saldo** tras cada operación y si llega a 0 (y venta no está cancelada) marca estado **`pagado`**.
- `invoicing`: emisión permitida únicamente con **venta pagada**. Operador puede **ver** comprobantes y **emitir** si corresponde; Admin puede **anular** y **configurar plantillas** (alineado al esquema global de permisos).

---

## 9) Tenancy (multi-empresa / sucursal)

- `EmpresaPermRequiredMixin` asegura: usuario autenticado, **empresa activa** válida, **membership activa**.
- Querysets y objetos en vistas de `payments` y `medios` se limitan a `self.empresa_activa`.
- `PaymentForm` filtra `medio` por empresa activa y solo **activos**.
- Validación extra en service y vistas: `medio.empresa_id == venta.empresa_id`.

---

## 10) Seguridad (defensa en profundidad)

1. **Templates** → Flags de UI (`puede_*`) para mostrar/ocultar/habilitar CTAs.
2. **Vistas** → `EmpresaPermRequiredMixin` + `required_perms` + filtros por empresa.
3. **Services** → Validaciones de negocio críticas (monto>0, tenant, idempotencia, sobrepago, recalcular saldo + FSM).

**Prohibido**:

- Consultar `EmpresaMembership.rol` directo en vistas o templates.
- Mezclar `LoginRequiredMixin` con `EmpresaPermRequiredMixin`.
- Crear helpers alternativos de permisos (`membership.has_perm`, etc.).
- Dejar restricciones solo en frontend.

---

## 11) Errores tratados / Idempotencia / Concurrencia

- **Idempotencia**: reintentos con la misma `idempotency_key` no duplican pagos; en split se usan claves derivadas.
- **Concurrencia**: `select_for_update()` sobre la Venta durante el registro y recálculo de saldo.
- **Sobrepago**: excepción `OverpayNeedsConfirmation` para confirmar split a propina; modal en front y fallback en server.

---

## 12) QA Manual (checklist)

1. **Medios** por empresa: crear “Efectivo”, “Transferencia” (activos).
2. Crear **Venta** con total ≈ 30.000 y **saldo_pendiente** = total.
3. Registrar **pago parcial** (10.000, no propina) → saldo = 20.000; estado **no** cambia a `pagado`.
4. Registrar **pago exacto** por el **saldo restante** → saldo = 0; estado pasa a **`pagado`**.
5. Registrar **propina** (marcada) → saldo **no** cambia; propinas suman aparte.
6. Intentar **sobrepago** (p. ej. 35.000 con saldo 30.000 y `es_propina=False`) → ver **modal/aviso de confirmación**; aceptar → se crean **2 pagos** (30.000 no propina + 5.000 propina); saldo = 0; estado `pagado`.
7. Reintentar el submit con la **misma `idempotency_key`** → no duplica (mismo pago/split), saldo consistente.
8. En `sales:detail`, ver **tabla de pagos** y **saldo** correcto tras cada operación.
9. Si la venta está `cancelado`, intentar registrar pagos → **bloquear** (mensaje).
10. Verificar que **operador** no ve “Configurar medios” ni puede acceder a rutas de medios (403/redirect con mensaje).

---

## 13) Roadmap inmediato

- **Reversa de pago** (soft delete/estado `revertido` + recalcular saldo + auditoría).
- **Cierres de caja**: resumen por medio, sucursal, rango. Monto de propinas separado.
- **Integración pasarelas** (MP/Stripe): usar `referencia` como id externo y **`idempotency_key`** origen pasarela.
- Roles finos adicionales (p. ej. **cajero**, **supervisor de caja**).

---

## 14) Notas de implementación

- Mantener el **cálculo de saldo** y **transición a `pagado`** **solo** en el **service** (`payments.services.payments`).
- Si se usan `signals`, delegar en el service (evitar duplicar reglas).
- Mensajería UI consistente con `django.contrib.messages` (success/info/warning/error).
- **Vistas de medios**: siempre filtrar por `self.empresa_activa` y proteger con `PAYMENTS_CONFIG`.

---

## 15) Diagramas de referencia

### 15.1 Secuencia registrar pago

```mermaid
sequenceDiagram
  participant U as Usuario
  participant VW as PaymentCreateView
  participant S as payments.services
  participant DB as PostgreSQL

  U->>VW: GET /ventas/<id>/pagos/nuevo/
  VW-->>U: Form (medio, monto, es_propina, referencia, key)

  U->>VW: POST form
  VW->>S: registrar_pago(...)
  alt monto > saldo y !es_propina y !auto_split
    S-->>VW: OverpayNeedsConfirmation(saldo, monto)
    VW-->>U: Re-render con aviso + hidden confirmar_split=1
    U->>VW: POST form (confirmar_split=1)
    VW->>S: registrar_pago(..., auto_split_propina=True)
    S->>DB: crear pago saldo + pago propina
  else pago simple
    S->>DB: crear pago único
  end
  S->>DB: recalcular_saldo + marcar_pagada si corresponde
  VW-->>U: Mensaje + redirect a sales:detail
```

### 15.2 Permisos declarativos (CBVs)

```mermaid
graph TD
  V[View] -->|hereda| EPRM[EmpresaPermRequiredMixin]
  EPRM -->|usa| ECM[EmpresaContextMixin]
  EPRM -->|valida| hasPerm["has_empresa_perm(user, empresa, perm)"]
  V -->|declara| RP["required_perms=(Perm.PAYMENTS_*,)"]
  V -->|context| Flags["puede_crear / puede_configurar"]
```

---

## 16) Apéndice — extracto de configuración de permisos

> **Referencia resumida** (la implementación real vive en `apps/org/permissions.py`).

```text
class Perm(str, Enum):
    # ...
    PAYMENTS_VIEW     = "PAYMENTS_VIEW"
    PAYMENTS_CREATE   = "PAYMENTS_CREATE"
    PAYMENTS_EDIT     = "PAYMENTS_EDIT"
    PAYMENTS_DELETE   = "PAYMENTS_DELETE"
    PAYMENTS_CONFIG   = "PAYMENTS_CONFIG"

ROLE_POLICY["admin"] |= {
    Perm.PAYMENTS_VIEW, Perm.PAYMENTS_CREATE, Perm.PAYMENTS_EDIT,
    Perm.PAYMENTS_DELETE, Perm.PAYMENTS_CONFIG,
}
ROLE_POLICY["operador"] |= {
    Perm.PAYMENTS_VIEW, Perm.PAYMENTS_CREATE,
}
ROLE_POLICY["supervisor"] |= {
    Perm.PAYMENTS_VIEW,
}
```

---

### Resumen ejecutivo

- **Pagos robustos** con idempotencia, tratamiento de **sobrepago** (modal/confirmación/split a propina) y **tenancy** garantizado.
- **Permisos granulares por rol**: admin (total), operador (uso diario), supervisor (consulta).
- **Seguridad en backend** (mixins + services); los templates solo reflejan flags de permiso para UX.
- Integración fluida con `sales` e `invoicing` (emisión con venta **pagada**).
- Código preparado para extensiones: reversa de pagos, cierres de caja e integración con pasarelas.

# Módulo 9 — `apps/invoicing` (Comprobantes no fiscales + numeración por sucursal)

> **Objetivo:** Emitir **comprobantes no fiscales** (p. ej. **REMITO** o **TICKET**) para **ventas pagadas**; numeración **atómica** por **Sucursal + Punto de Venta + Tipo**, guardar **snapshot inmutable** (ítems, totales, descuentos/promos, metadatos) y generar archivo **HTML** y (opcional) **PDF** imprimible.  
> **Stack:** Django (CBVs server-rendered) + Bootstrap 5 (UI/templating), renderer HTML→PDF.  
> **Estados relevantes:** La emisión requiere **`payment_status="pagada"`** (independiente del estado de proceso `borrador/en_proceso/terminado/cancelado`).

---

## 1) Estructura del módulo

```
apps/invoicing/
├─ __init__.py
├─ apps.py                           # name="apps.invoicing"
├─ admin.py                          # Admin de Comprobante / Secuencia
├─ migrations/
│  └─ __init__.py
├─ models.py                         # Comprobante, SecuenciaComprobante, TipoComprobante
├─ urls.py                           # Rutas: listado, detalle, descargar, emitir (desde venta)
├─ views.py                          # List, Detail, Emit (FormView), Download, públicos (print/download)
├─ forms/
│  ├─ __init__.py
│  └─ invoice.py                     # InvoiceEmitForm (tipo, cliente_facturacion opcional)
├─ services/
│  ├─ __init__.py
│  ├─ numbering.py                   # next_number(): numeración atómica (sucursal/tipo/punto_venta)
│  ├─ emit.py                        # emitir(): valida → numera → snapshot → render → persistencia
│  └─ renderers.py                   # render_html(context) y html_to_pdf(html) (opcional)
├─ selectors.py                      # por_rango(empresa, sucursal?, tipo?, desde?, hasta?)
├─ templates/
│  └─ invoicing/
│     ├─ list.html                   # Listado con filtros (fecha/sucursal/tipo)
│     ├─ emit.html                   # Form de emisión (modal de confirmación claro)
│     ├─ detail.html                 # Detalle del comprobante (metadatos + acciones)
│     └─ _invoice_print.html         # Plantilla imprimible A4 B/N (con “PAGADO”, descuentos/promos)
├─ static/
│  └─ invoicing/
│     ├─ invoicing.css               # Reglas mínimas para impresión (opcional)
│     └─ invoicing.js                # Mejoras UI (opcional)
└─ pdf/
   └─ storage_backend.md             # Notas de almacenamiento (MEDIA en dev; S3/GCS en prod)
```

**Cambios clave vs iteración anterior**

- Se **alineó** con la separación **`estado`** (proceso) / **`payment_status`** (pago) de `Venta`.
- **Form de emisión**: quedó **minimal** (Tipo + Cliente de facturación opcional). El **Punto de Venta** **no** lo pide el usuario; el sistema lo resuelve vía secuencia y/o `sucursal_activa.punto_venta` (si fue configurado).
- **Snapshot** incluye ahora **ajustes** (promos/desc.) con etiquetas listas para UI (`kind_label`), y totales derivados (**precio_lista_total**, **descuento_total**, **promo_total**, etc.).
- Plantilla **imprimible**: muestra **precio de lista**, **descuento/promoción** (si aplica) y un **sello “PAGADO”** (si `payment_status="pagada"`). **Propina** no figura en el total (se mantiene fuera del total imponible/operativo del comprobante).

---

## 2) Modelos (visión funcional)

### 2.1 `TipoComprobante` (enum)

- Valores actuales: `REMITO`, `TICKET`. Extensible.
- `choices` para forms/filters.

### 2.2 `SecuenciaComprobante`

- Claves: `sucursal(FK)`, `tipo (enum)`, `punto_venta (int)`, `proximo_numero (int)`.
- **Unicidad**: `(sucursal, tipo, punto_venta)`.
- Usada por `services/numbering.py` con **row lock** para asignar números de forma **atómica** y **concurrente-segura**.

### 2.3 `Comprobante`

- **Relaciones**: `empresa(FK)`, `sucursal(FK)`, `venta(OneToOne)` _(MVP: 1 venta → 1 comprobante)_, `cliente(FK)`, `cliente_facturacion(FK opc.)`, `emitido_por (User)`.
- **Numeración**: `tipo (enum)`, `punto_venta (int)`, `numero (int)` + propiedad `numero_completo` (formato `PPPP-NNNNNNNN`).
- **Valores**: `total`, `moneda`.
- **Snapshot**: `JSONField` **inmutable** (ítems, totales, ajustes, metadatos).
- **Archivos**: `archivo_html` (obligatorio), `archivo_pdf` (opcional).
- **Público opcional**: `public_key`, `public_expires_at`, `public_revocado` (para vista/descarga pública).

> **Cliente de facturación**: el modelo vive en **`apps.customers`** (`ClienteFacturacion`, OneToOne o perfil alternativo vinculado al cliente). Su uso es **opcional** y se ofrece solo si existe un perfil.

---

## 3) Snapshot (contrato)

**Estructura mínima (ejemplo):**

```json
{
  "comprobante": {
    "tipo": "TICKET",
    "numero": "0001-00001234",
    "emitido_en": "2025-10-01T00:00:00-03:00",
    "moneda": "ARS"
  },
  "empresa": {
    "id": 8,
    "nombre": "Lavadero XYZ",
    "logo_data": "data:image/png;base64,..."
  },
  "sucursal": { "id": 3, "nombre": "Casa Central", "punto_venta": "1" },
  "cliente": {
    "id": 21,
    "nombre": "Juan",
    "apellido": "Pérez",
    "cuit": "20-12345678-9",
    "domicilio": "Av. Siempreviva 742",
    "localidad": "San Miguel",
    "iva": "RI"
  },
  "cliente_facturacion": {
    "razon_social": "EMPRESA SA",
    "cuit": "30-12345678-9",
    "cond_iva": "RI",
    "domicilio_fiscal": "Ruta 9 km 123, Tucumán"
  },
  "vehiculo": { "id": 10, "patente": "ABC123", "tipo": "Pick-up" },
  "venta": {
    "id": "1c8dd985-9984-469f-9891-b8f9f4f8b595",
    "estado": "terminado",
    "payment_status": "pagada",
    "subtotal": "35000.00",
    "descuento": "2000.00",
    "propina": "0.00",
    "total": "33000.00",
    "saldo_pendiente": "0.00",
    "notas": ""
  },
  "items": [
    {
      "servicio_id": 5,
      "servicio_nombre": "Lavado Full",
      "cantidad": 1,
      "precio_unitario": "35000.00",
      "subtotal": "35000.00"
    }
  ],
  "ajustes": [
    {
      "scope": "venta",
      "kind": "promo",
      "kind_label": "Promoción",
      "label": "Promo Primavera -10%",
      "monto": "3500.00",
      "porcentaje": true,
      "target": null
    },
    {
      "scope": "venta",
      "kind": "descuento_manual",
      "kind_label": "Descuento",
      "label": "Redondeo",
      "monto": "500.00",
      "porcentaje": false,
      "target": null
    }
  ],
  "totales": {
    "precio_lista_total": "35000.00",
    "promo_total": "3500.00",
    "descuento_total": "500.00"
  },
  "leyendas": { "no_fiscal": "Documento no fiscal." }
}
```

**Notas**

- **`ajustes`** lista **promociones y descuentos** (por venta o por ítem) con: `scope`, `kind`, **`kind_label`** (texto listo: “Promoción”/“Descuento”), `label`, `monto`, `porcentaje`, `target` (si aplica a un servicio puntual).
- **`totales`** agrega sumatorias útiles para la plantilla: **`precio_lista_total`**, **`promo_total`**, **`descuento_total`**.
- **`payment_status`** persiste el estado de pago en el momento de emisión (drive de “PAGADO”).
- El snapshot se valida (JSON-serializable) y **no se muta** luego de emitirse el comprobante.

---

## 4) Servicios

### 4.1 Numeración — `services/numbering.py`

```python
next_number(sucursal, tipo, punto_venta) -> ctx
# ctx: { punto_venta: int, numero: int, numero_completo: "PPPP-NNNNNNNN" }
```

- Resuelve/crea `SecuenciaComprobante` y **incrementa** bajo transacción.
- El **punto de venta** puede venir de `Sucursal` (config app org) y/o por parámetro. En UI, **no se solicita**; lo resuelve el backend/secuencia.

### 4.2 Emisión — `services/emit.py`

```python
emitir(
  *, venta_id, tipo: str, punto_venta: int = 1,
  cliente_facturacion_id: int | None = None,
  actor: User | None = None,
  reintentos_idempotentes: bool = True,
) -> EmitirResultado  # { comprobante, creado: bool }
```

**Validaciones y flujo:**

1. Cargar `Venta` con relaciones necesarias.
2. Exigir `payment_status == "pagada"` y **no** `estado == "cancelado"`.
3. Si ya existe comprobante y `reintentos_idempotentes=True` → devolver existente (`creado=False`).
4. `next_number(...)` por `(sucursal, tipo, punto_venta)`.
5. Construir **snapshot** (ítems, ajustes, totales).
6. Render HTML (+ PDF opcional), persistir archivos y registro `Comprobante`.
7. (Opcional) **Auto-emisión** (`emitir_auto(...)`) disponible para flujos que lo requieran (por defecto **OFF**; controlado a nivel app/setting).

---

## 5) Formularios

### 5.1 `InvoiceEmitForm`

- **Campos**:
  - `tipo` (`TipoComprobante.choices`).
  - `cliente_facturacion`: `ModelChoiceField` sobre perfiles **del cliente operativo actual** (si existe). Si el cliente **no** tiene perfil, el campo no se muestra en la UI.
- **UI Rules**: clases Bootstrap; validaciones livianas; **sin** campo de **punto de venta** (lo decide el sistema).

---

## 6) Vistas + URLs + Seguridad

### 6.1 URLs (`namespace="invoicing"`)

```
GET   /comprobantes/                               name="invoicing:list"
GET   /comprobantes/<uuid:pk>/                     name="invoicing:detail"
GET   /comprobantes/<uuid:pk>/descargar/           name="invoicing:download"
GET   /public/comprobantes/<key>/                  name="invoicing:public_view"      # sin auth
GET   /public/comprobantes/<key>/descargar/        name="invoicing:public_download"  # sin auth

# Inicio desde venta:
GET   /ventas/<uuid:venta_id>/emitir/              name="invoicing:emit"
POST  /ventas/<uuid:venta_id>/emitir/              name="invoicing:emit"
```

### 6.2 Seguridad declarativa (permisos)

- **Fuente de verdad**: `apps.org.permissions.Perm` + `ROLE_POLICY`.
- **Mixins**: todas las vistas usan `EmpresaPermRequiredMixin` (con Tenancy). **No** mezclar con `LoginRequiredMixin` directo.
- **Perms sugeridos** para este módulo:
  - `INVOICING_VIEW` → listar/ver comprobantes.
  - `INVOICING_EMIT` → emitir comprobante desde venta.
  - `INVOICING_DOWNLOAD` → descargar archivo del comprobante.
- **Tenancy**: todos los querysets filtran por **empresa activa**; descarga valida propiedad.

### 6.3 Vistas

- `ComprobanteListView` → filtros por sucursal/tipo/fechas vía `selectors.por_rango(...)` (siempre por empresa activa).
- `ComprobanteDetailView` → `select_related` (empresa, sucursal, venta, cliente, cliente_facturacion, emitido_por) y filtro por empresa.
- `EmitirComprobanteView` → valida `payment_status="pagada"`. Form minimal con confirmación (modal). Flag `puede_emitir` calculado en contexto.
- `ComprobanteDownloadView` → sirve **PDF** si existe; si no, **HTML**. Filtro por empresa.
- `PublicInvoiceView/PublicInvoiceDownloadView` → ver/descargar por `public_key` con control de expiración y revocación.

---

## 7) Plantillas (UX)

### 7.1 `emit.html` (resumen)

- Breadcrumbs + header claros.
- Avisos:
  - Si **no pagada** → alerta **warning** (no deja emitir).
  - Si **ya tiene comprobante** → alerta **info** con link a detalle.
- **Formulario simple**:
  - **Tipo** (select).
  - **Cliente de facturación** (solo si el cliente tiene perfil de facturación cargado).
- **Modal de confirmación** con lenguaje claro orientado a usuario (“Vamos a generar el comprobante… no se puede deshacer… crear PDF/HTML para imprimir o enviar”).

### 7.2 `list.html`

- Filtros por **Sucursal**, **Tipo**, **Desde/Hasta**.
- Tabla con: **N°**, **Tipo**, **Sucursal**, **Cliente**, **Total**, **Emitido**, **Acciones** (Ver / Descargar).
- Paginación server-side.

### 7.3 `detail.html`

- Header con **N° completo**, **Tipo**, **Emitido** (fecha/hora).
- Panel **Resumen**: Empresa/Sucursal, Moneda, Total, Cliente (operativo) y, si aplica, **Cliente de facturación**.
- Panel **Cliente y Venta**: cliente, venta, vehículo, estado de venta (badge), notas.
- Tabla **Ítems** (servicio, precio, subtotal) + footer (subtotal, descuento, total).
- Acciones: Ver/Descargar archivo (HTML/PDF).

### 7.4 `_invoice_print.html` (A4 B/N)

- **Encabezado**: logo (o placeholder), Empresa + Sucursal (dirección opcional), título (`REMITO`/`TICKET`), leyenda (_Documento no fiscal_), N° y fecha.
- **Datos de Cliente**:
  - Bloque del **cliente operativo**.
  - Bloque **Facturado a** (solo si hay **Cliente de facturación**).
- **Ítems** con columnas: CANTIDAD, DESCRIPCIÓN, P. UNIT., PARCIAL.
- **Totales** al pie:
  - **Precio de lista** (suma de parciales).
  - **Promociones aplicadas** (si las hubo).
  - **Descuentos** (si los hubo).
  - **TOTAL** (importe final cobrado; **propina no** forma parte).
- **Sello “PAGADO”** (si `payment_status="pagada"`): marca visual en layout (sin color).
- **Observaciones** y **firmas** (entregué/recibí).

---

## 8) Selectors

### 8.1 `selectors.por_rango(empresa, sucursal=None, tipo=None, desde=None, hasta=None)`

- Devuelve `QuerySet` de `Comprobante` filtrado por empresa y opcionalmente sucursal/tipo/fechas (inclusive por día).
- `select_related`: `empresa`, `sucursal`, `venta`, `cliente` (optimiza listados).

---

## 9) Integraciones

- **Sales (`apps/sales`)**: en `sales:detail`, la tarjeta **Comprobante** usa flags:
  - `venta_pagada` (por `payment_status`), `ya_tiene_comprobante`, `puede_emitir`.
  - Si se puede emitir → CTA a `invoicing:emit`. Si ya existe → **Ver/Descargar**.
- **Payments (`apps/payments`)**: cuando el service de pagos deja `saldo=0`, muta **`payment_status="pagada"`** (independiente de `estado`). Esto habilita la emisión.
- **Customers (`apps.customers`)**: `ClienteFacturacion` OneToOne/perfil; si existe, se ofrece en el form de emisión y queda reflejado en el snapshot.

---

## 10) Seguridad y Tenancy

- **Tenancy**: todas las vistas usan `EmpresaPermRequiredMixin` (resuelve `empresa_activa`, membership, etc.).
- **Permisos** (sugerencia, fuente de verdad en `apps.org.permissions`):
  - `INVOICING_VIEW` → ver/listar.
  - `INVOICING_EMIT` → emitir.
  - `INVOICING_DOWNLOAD` → descargar.
- **Defensa en profundidad**: templates solo reflejan **flags** para UX; la seguridad real vive en **mixins** (CBV) y **services** (reglas/validaciones).

---

## 11) QA Manual (checklist)

1. **Venta pagada** (`payment_status="pagada"`) y **no cancelada** → `Emitir` disponible; crea `Comprobante` + archivos.
2. **Reintento** de emisión sobre la misma venta (con `reintentos_idempotentes=True`) → devuelve existente (**mensaje info**).
3. **Listado**: filtros por sucursal/tipo/fecha, paginado y conteo.
4. **Detalle**: muestra N°, tipo, fecha, cliente (y facturación si aplica), ítems y totales.
5. **Imprimible**: sello **PAGADO** si corresponde; **precio de lista**, **promociones** y **descuentos** si existieron; **propina** no se suma al total.
6. **Descarga**: entrega **PDF** si existe; si no, **HTML** con `content-type` correcto.
7. **Tenancy**: intentar acceder a comprobante de otra empresa → 404/redirect seguro.
8. **Cliente de facturación**: si el cliente tiene perfil, aparece en form; si no, no “hace ruido”.
9. **Número**: respeta secuencia por `(sucursal, tipo, punto_venta)` bajo concurrencia (sin saltos erráticos).

---

## 12) Roadmap

- **Anulación / Nota de crédito** (no fiscal) con encadenamiento.
- **Exportes** (CSV/PDF por rango/filters).
- **Impresión térmica** (layout chico).
- **Campos fiscales por país** (si escala a integración AFIP/CAE u otros).
- **Compartir público**: links con expiración y revocación ya soportados (UI pendiente).

---

## 13) Flujo de alto nivel

```mermaid
sequenceDiagram
  participant U as Operador
  participant PAY as Payments
  participant SALES as Sales
  participant INV as Invoicing
  participant DB as DB

  U->>SALES: Ver detalle de venta
  U->>PAY: Registrar pagos (si corresponde)
  PAY->>DB: Persistir pagos + recalcular saldo
  alt saldo == 0
    PAY->>DB: Venta.payment_status = "pagada"
  end

  U->>INV: Emitir comprobante (tipo, cliente_facturación?)
  INV->>DB: next_number(sucursal, tipo, ptoV) (atomic)
  INV->>DB: Guardar Comprobante + snapshot + archivo HTML/PDF
  DB-->>U: OK (número, enlaces Ver/Descargar)
```

---

### Resumen ejecutivo

- Emisión **idempotente** para **ventas pagadas** con numeración **atómica** por sucursal/tipo/punto de venta.
- **Snapshot** rico (ítems, ajustes y totales derivados) → plantillas claras: **precio de lista**, **descuento/promos** y sello **PAGADO**.
- **Form minimal** (cero ruido): solo **Tipo** y, si aplica, **Cliente de facturación**.
- Tenancy, permisos y CBVs alineados al estándar del proyecto.
- Integrado con `sales` y `payments`; listo para crecer a anulaciones/exportes/impresoras térmicas.

# Módulo 10 — `apps/notifications` (Plantillas y Log de Notificaciones)

> **Objetivo del módulo:** Gestionar **plantillas** de mensajes (Email/WhatsApp/SMS — simulado en MVP), **renderizarlas** con datos de la venta/cliente, y **registrar** cada envío en un **log** con su estado.  
> En el MVP no se integra un proveedor real: el “envío” es simulado y auditable.

---

## 1) Estructura de carpetas/archivos

```
apps/notifications/
├─ __init__.py
├─ apps.py                         # Config de la app (name="apps.notifications")
├─ admin.py                        # Registro de PlantillaNotif y LogNotif en admin
├─ migrations/
│  └─ __init__.py
├─ models.py                       # Modelos: PlantillaNotif, LogNotif
├─ urls.py                         # Todas las rutas (CRUD plantillas, enviar desde venta)
├─ views.py                        # Vistas server-rendered (CRUD plantillas, acción enviar/preview)
├─ forms/
│  ├─ __init__.py
│  └─ template.py                  # Form de creación/edición de plantilla
├─ services/
│  ├─ __init__.py
│  ├─ renderers.py                 # Render de plantilla con contexto (venta, cliente, empresa)
│  └─ dispatcher.py                # Orquestación de envío simulado + persistencia de LogNotif
├─ selectors.py                    # Lecturas: listar plantillas activas, logs por venta/fecha
├─ templates/
│  └─ notifications/
│     ├─ templates_list.html       # Listado de plantillas
│     ├─ template_form.html        # Alta/edición de plantilla (con ayuda memoria de variables)
│     ├─ preview.html              # Vista previa con variables de muestra
│     └─ send_from_sale.html       # Pantalla para enviar notificación de una venta
├─ static/
│  └─ notifications/
│     ├─ notifications.css         # Estilos propios
│     └─ notifications.js          # UX: copiar cuerpo, reemplazos en vivo (preview)
└─ emails/
   └─ generic_subject.txt          # (Opcional) asunto por defecto si canal=email
```

### Rol de cada componente

- **`models.py`**:
  - `PlantillaNotif(empresa, clave, canal, cuerpo_tpl, activo)` — ej.: `canal ∈ {email, whatsapp}`.
  - `LogNotif(venta, canal, destinatario, cuerpo_renderizado, estado, enviado_en)` — traza histórica.
- **`services/renderers.py`**: compone **contexto** (cliente, vehículo, venta, empresa) y rinde `cuerpo_tpl` → `cuerpo_renderizado`.
- **`services/dispatcher.py`**: simula el **envío** según `canal` y crea `LogNotif` con `estado ∈ {enviado, error}`.
- **`selectors.py`**: listados de plantillas activas; logs por venta/fecha/canal.
- **`views.py`**: CRUD de plantillas y acción **enviar** (desde una venta).
- **`urls.py`**: concentra tanto las rutas de plantillas como la acción `/ventas/<id>/notificar/`.

---

## 2) Endpoints propuestos

- `GET  /notificaciones/plantillas/` → Listado.
- `GET  /notificaciones/plantillas/nueva/` → Alta plantilla.
- `POST /notificaciones/plantillas/nueva/` → Crear.
- `GET  /notificaciones/plantillas/<uuid:id>/editar/` → Edición.
- `POST /notificaciones/plantillas/<uuid:id>/editar/` → Actualizar.
- `GET  /ventas/<uuid:venta_id>/notificar/` → Form para elegir **plantilla** y **destinatario** (autocompleta con cliente).
- `POST /ventas/<uuid:venta_id>/notificar/` → Render + “envío” simulado + creación de `LogNotif`.
- `GET  /notificaciones/logs/` → (Opcional) Listado de logs con filtros por fecha/venta/canal/estado.

> La UI natural agrega un botón **“Notificar cliente”** en el **detalle de la venta** cuando está `terminado` o `pagado`.

---

## 3) Contratos de entrada/salida (conceptual)

### Crear/Editar Plantilla

- **Input (POST)**:  
  `clave` (única por empresa), `canal` (`email`/`whatsapp`), `cuerpo_tpl` (texto con `{{variables}}`), `activo`.
- **Proceso**: persistir plantilla; validar que `clave` no se repita.
- **Output**: plantilla lista para usar en envíos.

### Enviar Notificación desde una Venta

- **Input (POST)**:  
  `venta_id`, `plantilla_id`, `destinatario` (email o teléfono), **contexto adicional opcional** (`nota_extra`).
- **Proceso**:
  1. `renderers.render(plantilla, venta, extras)` → `cuerpo_renderizado`.
  2. `dispatcher.send(canal, destinatario, cuerpo_renderizado)` (simulado).
  3. Crear `LogNotif(venta, canal, destinatario, cuerpo_renderizado, estado, enviado_en=now)`.
- **Output (UI)**: redirect al detalle de la venta con mensaje de éxito/error.

### Preview

- **Input (GET/POST)**: `plantilla_id`, `venta_id` (opcional).
- **Proceso**: render con **datos de ejemplo** o con una venta real.
- **Output**: `preview.html` mostrando el cuerpo final.

---

## 4) Variables soportadas en plantillas (MVP sugerido)

- `{{cliente.nombre}}`, `{{cliente.apellido}}`, `{{cliente.telefono}}`
- `{{vehiculo.patente}}`, `{{vehiculo.marca}}`, `{{vehiculo.modelo}}`
- `{{venta.id}}`, `{{venta.total}}`, `{{venta.estado}}`
- `{{empresa.nombre}}`, `{{sucursal.nombre}}`
- `{{venta.comprobante_url}}` (link público al comprobante en invoicing, si existe)
- `{{nota_extra}}` (dato libre desde el form de envío)

> El **renderer** maneja faltantes con `"—"` para no romper el envío.  
> En los templates se muestra una “ayuda memoria” con todas estas variables.

---

## 5) Dependencias e integraciones

- **Depende de `sales`**: para cargar venta/cliente/vehículo y validar empresa activa.
- **Usado por `invoicing`**: incluir `link` a comprobante público en el mensaje.
- **Transversal**: `org` (empresa/sucursal) para contexto.

---

## 6) Seguridad

- Solo usuarios autenticados y con permiso en la **empresa activa**.
- Validar que la **venta** pertenezca a la empresa.
- Sanitizar variables en el render para evitar inyección.
- Los links públicos de comprobantes son **read-only** y no requieren login, pero se generan con un **`public_key` UUID** para seguridad por ofuscación.

---

## 7) Roadmap inmediato

1. Modelos `PlantillaNotif` y `LogNotif`.
2. Renderer de variables con contexto de venta y valores por defecto.
3. Dispatcher simulado + creación de `LogNotif`.
4. Vistas y templates: CRUD de plantillas, “Enviar desde venta” y “Preview”.
5. Enlace claro en `/ventas/<id>/` para notificar al cliente.
6. Logs de notificación visibles por admins o staff para auditoría.

# Módulo 11 — `apps/cashbox` (Cierres de Caja)

> **Objetivo del módulo:** Gestionar el **ciclo de caja** en cada sucursal: apertura obligatoria antes de operar, un único cierre abierto por sucursal a la vez, consolidación automática de pagos y propinas, y registro de notas y trazabilidad de usuarios.

---

## 1) Estructura de carpetas/archivos

```
apps/cashbox/
├─ __init__.py
├─ apps.py                        # Config de la app (name="apps.cashbox")
├─ admin.py                       # Admin de CierreCaja y CierreCajaTotal (solo lectura/auditoría)
├─ migrations/
│  └─ __init__.py
├─ models.py                      # CierreCaja y CierreCajaTotal
├─ urls.py                        # Endpoints: abrir, cerrar, detalle, listado
├─ views.py                       # Vistas server-rendered CRUD (abrir/cerrar, detalle, listado)
├─ forms/
│  ├─ __init__.py
│  └─ closure.py                  # Validaciones de cierre (ej. notas obligatorias si hay diferencias)
├─ services/
│  ├─ __init__.py
│  ├─ cashbox.py                  # abrir_cierre(), cerrar_cierre() con reglas de negocio
│  └─ totals.py                   # Calcular totales de pagos por método y propinas
├─ selectors.py                   # Consultas optimizadas: cierres por rango, detalle con totales
├─ templates/
│  └─ cashbox/
│     ├─ list.html                # Listado de cierres por sucursal
│     ├─ form.html                # Form de apertura/cierre (notas, confirmación)
│     ├─ detail.html              # Detalle de un cierre con desglose de totales
│     └─ _totals_table.html       # Partial con tabla de métodos de pago/propinas
└─ static/
   └─ cashbox/
      ├─ cashbox.css              # Estilos propios
      └─ cashbox.js               # UX: confirmación, recálculo de totales en vivo
```

---

## 2) Modelos

### `CierreCaja`

- **Tenancy**: `empresa`, `sucursal`.
- **Usuario**: `usuario` que abre, `cerrado_por` que cierra.
- **Fechas**: `abierto_en` automático (now), `cerrado_en` al momento del cierre.
- **Estado**: exactamente **un cierre abierto por sucursal** (constraint parcial).
- **Notas**: comentarios, observaciones o diferencias.
- **Helpers**: `esta_abierta`, `rango()`.

### `CierreCajaTotal`

- Relacionado a `CierreCaja`.
- Campos: `medio` (forma de pago), `monto`, `propinas`.
- Usado para almacenar el resumen generado por `services.totals`.

---

## 3) Servicios

### `services/cashbox.py`

- **`abrir_cierre(empresa, sucursal, usuario)`**:
  - Verifica que no exista cierre abierto en esa sucursal.
  - Crea `CierreCaja(abierto_en=now)`.
- **`cerrar_cierre(cierre, usuario, notas)`**:
  - Calcula totales de pagos con `services.totals`.
  - Marca `cerrado_en=now`, `cerrado_por=usuario`.
  - Crea registros `CierreCajaTotal` por cada método de pago.

### `services/totals.py`

- Resume pagos (`apps.payments.Pago`) desde `abierto_en` hasta `cerrado_en`.
- Devuelve {medio → monto, propinas}.

---

## 4) Selectors

- `cierres_por_rango(empresa, sucursal, desde, hasta)` → lista de cierres con filtros.
- `detalle_con_totales(cierre_id)` → incluye `CierreCajaTotal`.

---

## 5) Vistas y URLs

### Rutas (`apps/cashbox/urls.py`)

- `GET  /caja/` → listado de cierres por sucursal.
- `GET  /caja/abrir/` → form de apertura.
- `POST /caja/abrir/` → ejecutar apertura.
- `GET  /caja/<uuid:id>/` → detalle de cierre.
- `GET  /caja/<uuid:id>/cerrar/` → form de cierre con totales precargados.
- `POST /caja/<uuid:id>/cerrar/` → confirmar cierre.

### Integración

- Al **iniciar sesión**, si no hay caja abierta → forzar apertura.
- Al **cerrar sesión**, si hay caja abierta → forzar cierre.

---

## 6) Seguridad

- Autenticación obligatoria.
- Validación multi-tenant: solo cierres de `empresa_activa`.
- Solo roles **cajero** y **admin** pueden abrir/cerrar.
- Constraints garantizan que solo haya **1 caja abierta por sucursal**.

---

## 7) Dependencias e integraciones

- **payments**: origen de pagos para totales.
- **sales**: contexto de ventas del rango.
- **org**: empresa y sucursal para tenancy.
- Integración en `sales`: bloquear ventas si no hay caja abierta en la sucursal del usuario.

---

## 8) Roadmap

1. Automatizar apertura/cierre forzando flujo en login/logout.
2. Dashboard con comparación “totales de sistema” vs. “efectivo contado”.
3. Exportación de cierres a CSV/PDF para auditoría.
4. Soporte a arqueo intermedio (cortes parciales de caja).

# Módulo 12 — `apps/saas` (Planes y Suscripciones)

> **Objetivo del módulo:** Administrar **planes** del SaaS y **suscripciones** de cada Empresa. Controlar límites (soft) y estado de facturación en un **MVP sin pasarela**.  
> **UX actual:**
>
> - El usuario ve su **panel** con plan/estado/uso y un **catálogo de planes** para solicitar upgrade.
> - **Toda** la administración real de Planes y Suscripciones se hace en **Django Admin** (no hay CRUD público).

---

## 1) Estructura de carpetas/archivos (viva)

```
apps/saas/
├─ __init__.py
├─ apps.py                       # Config de la app (name="apps.saas")
├─ admin.py                      # Admin de PlanSaaS y SuscripcionSaaS
├─ migrations/
│  └─ __init__.py
├─ models.py                     # PlanSaaS, SuscripcionSaaS
├─ urls.py                       # /saas/panel/, /saas/planes/, /saas/upgrade/
├─ views.py                      # Panel empresa + catálogo público + acción POST upgrade
├─ forms/
│  ├─ __init__.py
│  ├─ plan.py                    # ModelForm (uso en admin/soporte si se necesitara)
│  └─ subscription.py            # ModelForm (idem)
├─ services/
│  ├─ __init__.py                # ServiceError, ServiceResult
│  ├─ plans.py                   # create/update/set_default (planes)
│  └─ subscriptions.py           # ensure_default, change_plan, confirm_paid_cycle, etc.
├─ selectors.py                  # planes_activos, suscripcion_snapshot, ...
├─ limits.py                     # gating soft: can_create_* y snapshots de uso
├─ templates/
│  └─ saas/
│     ├─ panel.html              # Panel de la empresa (plan vigente + uso + CTA)
│     └─ planes_public.html      # Catálogo público de planes (usuarios logueados)
└─ policies/
   └─ gating.md                  # Lineamientos de “gating” por plan (referencial)
```

> **Eliminados** del árbol (ya no se usan): `plans_list.html`, `plan_form.html`, `subs_list.html`, `sub_form.html` y las vistas CRUD públicas.

---

## 2) Endpoints (actuales)

- `GET  /saas/panel/` → **Panel** de la empresa activa: plan, estado (vigente/trial/suspendida), y **uso vs límites** (sucursales, usuarios, empleados de sucursal activa).
- `GET  /saas/planes/` → **Catálogo público** de planes (todo usuario autenticado). Muestra precio, límites y badges “recomendado/trial”.
- `POST /saas/upgrade/` → Acción de **“Solicitar upgrade”** (MVP: registra intención con mensaje; no cambia plan ni cobra).

> **Backoffice real** (crear/editar Planes y Suscripciones): **Django Admin**.

---

## 3) Contratos (conceptual)

### Plan (`PlanSaaS`)

- **Campos clave:** `nombre`, `descripcion`, `activo`, `default`, `trial_days`,  
  `max_empresas_por_usuario`, `max_sucursales_por_empresa`,  
  `max_usuarios_por_empresa`, `max_empleados_por_sucursal`, `max_storage_mb`,  
  `precio_mensual`, `external_plan_id`.
- **Salida típica (UI):** nombre, precio, límites y badges (default/trial).

### Suscripción (`SuscripcionSaaS`)

- **Relación:** `empresa (OneToOne) → plan (FK)`.
- **Estado funcional (`estado`):** `activa | vencida | suspendida`.
- **Pago (`payment_status`):** `trial | paid | unpaid | past_due` (informativo en MVP).
- **Fechas:** `inicio`, `fin` (vigencia funcional).
- **Cálculos:** `vigente`, `trial_ends_at`, `is_trialing`.

### Panel (empresa)

- **Input:** empresa activa (de sesión/middleware).
- **Proceso:** `suscripcion_snapshot(empresa)` + `get_usage_snapshot(empresa, sucursal)`.
- **Output:** plan/estado/fechas + uso vs límites y **CTA** de upgrade.

---

## 4) Dependencias e integraciones

- **`apps/org`**:

  - **Onboarding** de empresa debe invocar
    ```python
    ensure_default_subscription_for_empresa(empresa=empresa)
    ```
    para asignar automáticamente el **plan default** (con trial si corresponde).
  - Los flujos de **crear sucursal** / **invitar empleado** pueden llamar a `limits.can_create_sucursal(empresa)` y `limits.can_add_empleado(sucursal)` para mostrar **avisos** (o bloquear si activás enforcement duro).

- **`apps/accounts`**:

  - Para contar usuarios/membresías activas en `limits.py`.

- **Tenancy middleware**:
  - Expone `request.empresa_activa` y `request.sucursal_activa` (requeridos por el panel y algunos contadores).

---

## 5) Seguridad

- **Panel `/saas/panel/`**: requiere usuario autenticado y empresa activa.
- **Catálogo `/saas/planes/`**: requiere usuario autenticado (no requiere empresa activa).
- **Upgrade `/saas/upgrade/`**: `POST` y requiere empresa activa.
- **Admin Django**: restringe Planes/Suscripciones a staff/superuser.

---

## 6) Límites (gating)

- Implementados en **`limits.py`** como **“soft”** por defecto:
  - `can_create_empresa(user)` → usa plan **default** como política global (L1).
  - `can_create_sucursal(empresa)` (L2).
  - `can_add_empleado(sucursal)` (L3).
  - `can_add_usuario_a_empresa(empresa)` (opcional).
- **Snapshot** de uso: `get_usage_snapshot(empresa, sucursal)` → alimenta UI del panel.
- **Enforcement duro (opcional):**
  ```python
  # settings.py
  SAAS_ENFORCE_LIMITS = True
  ```
  Si está `True`, los `GateResult.should_block()` permiten bloquear creaciones en los servicios/vistas de `org`.

---

## 7) Flujo de upgrades (MVP y escalabilidad)

- **MVP (actual):**

  - El usuario ve `/saas/planes/` y **POST** `/saas/upgrade/`.
  - Mostramos **mensaje** de interés; **no** cambiamos plan ni cobramos.
  - Vos cambiás plan desde **Admin** o, si querés, podemos activar en el POST:
    ```python
    change_plan(empresa=empresa, nuevo_plan=plan, keep_window=True)
    ```
    (deshabilitado por ahora para no sorprender).

- **Trial 30 días (listo):**

  - `PlanSaaS.trial_days` + `SuscripcionSaaS.payment_status="trial"` al crear la suscripción default.
  - `trial_ends_at` se muestra en el panel.

- **Pasarela (futuro, p. ej. Mercado Pago):**
  - POST `/saas/upgrade/` inicia checkout → al **webhook de pago**:  
    `confirm_paid_cycle(empresa=empresa, months=1, external_subscription_id=..., ...)`  
    que actualiza `payment_status="paid"`, fechas y `fin`.

---

## 8) Integración con `org` (puntos de anclaje)

- **Onboarding Empresa** → después de `EmpresaCreateView` exitoso:
  ```python
  from apps.saas.services.subscriptions import ensure_default_subscription_for_empresa
  ensure_default_subscription_for_empresa(empresa=empresa)
  ```
- **Crear Sucursal (Org)** → previo a persistir:
  ```python
  from apps.saas.limits import can_create_sucursal
  gate = can_create_sucursal(empresa)
  # mostrar gate.message como warning; si SAAS_ENFORCE_LIMITS=True y gate.should_block(): abortar
  ```
- **Crear/Invitar Empleado (Org)** → previo a persistir:
  ```python
  from apps.saas.limits import can_add_empleado, can_add_usuario_a_empresa
  gate1 = can_add_usuario_a_empresa(empresa)
  gate2 = can_add_empleado(sucursal)
  ```
- **Navbar** → link visible a `/saas/panel/` para usuarios autenticados.

---

## 9) Verificación rápida

1. **Crear planes** en **Admin** (marcar uno como **default**).
2. Crear una **empresa** → se asigna suscripción automáticamente (trial si aplica).
3. **Panel `/saas/panel/`**: se visualiza plan/estado/uso.
4. **Catálogo `/saas/planes/`**: cards con precios y límites; botón de **Solicitar upgrade** (POST).
5. Probar límites (crear sucursales/usuarios) y recibir **avisos** (soft).
6. (Opcional) Activar `SAAS_ENFORCE_LIMITS=True` y validar **bloqueo** en flows de `org`.

---

## 10) Decisiones y razones

- **CRUD público eliminado**: administración real via **Django Admin** (más simple y seguro).
- **Catálogo público** y **Panel** separados: UX clara (info + upsell).
- **States separados**: `estado` (funcional) vs. `payment_status` (pago); necesario para pasarela.
- **Gating en `limits.py`**: centralizado y **conmutable** (soft → hard) por `settings`.

---

## 11) Roadmap corto

1. Hook de **backfill**: script para `ensure_default_subscription_for_empresa` sobre empresas legadas.
2. Conectar **gating** en `org` (views de sucursales/empleados) con mensajes Bootstrap.
3. (Opcional) Habilitar que `/saas/upgrade/` haga `change_plan` automático en entornos de demo.
4. Integrar **pasarela** (Mercado Pago): checkout + webhooks → `confirm_paid_cycle`.

# Módulo 13 — `apps/audit` (Auditoría de Cambios y Accesos)

> **Objetivo del módulo:** Registrar eventos de **auditoría** (quién hizo qué y cuándo) sobre modelos y vistas clave del sistema. En el MVP: traza mínima de **accesos a vistas sensibles** y **mutaciones** (create/update/delete) con un **diff** compacto.

---

## 1) Estructura de carpetas/archivos

```
apps/audit/
├─ __init__.py
├─ apps.py                      # Config de la app (name="apps.audit")
├─ admin.py                     # Registro de AuditEvent en admin
├─ migrations/
│  └─ __init__.py
├─ models.py                    # Modelo: AuditEvent
├─ urls.py                      # Rutas: listado y detalle (opcional en MVP)
├─ views.py                     # Vistas server-rendered (listado/filtrado de auditoría)
├─ middleware.py                # Middleware: registra accesos a vistas marcadas como sensibles
├─ hooks/
│  ├─ __init__.py
│  ├─ django_signals.py         # Conexiones a post_save/post_delete para modelos clave
│  └─ audit_helpers.py          # Helpers para construir diffs y normalizar payloads
├─ services/
│  ├─ __init__.py
│  └─ audit_log.py              # API interna: write_event(actor, action, object_ref, diff, meta)
├─ selectors.py                  # Lecturas: filtrar eventos por fecha/usuario/modelo/empresa
├─ templates/
│  └─ audit/
│     ├─ list.html              # Listado con filtros
│     └─ detail.html            # Vista detalle de un evento (payload/diff)
└─ static/
   └─ audit/
      ├─ audit.css              # Estilos (enfatizar campos cambiados)
      └─ audit.js               # UX (toggle JSON pretty-print, filtros)
```

### Rol de cada componente

- **`models.py`**: `AuditEvent(empresa, usuario, accion, tabla, fila_pk, diff_json, meta_json, creado_en)`; `accion ∈ {create, update, delete, access}`.
- **`middleware.py`**: registra `access` para vistas marcadas (por convención: añadir un atributo en la vista o usar path regex).
- **`hooks/django_signals.py`**: conecta `post_save`/`post_delete` para modelos críticos (Venta, Pago, Comprobante, PrecioServicio, etc.) y construye el **diff** con `audit_helpers`.
- **`services/audit_log.py`**: punto único de escritura; asegura normalización y control de tamaño de `diff_json`.
- **`selectors.py`**: consultas para reportes/filtrado.
- **`templates/audit/*`**: interfaz simple para inspección (opcional en MVP).

---

## 2) Endpoints propuestos

- `GET  /audit/` → Listado de eventos con filtros: fecha (rango), usuario, modelo, acción, empresa/sucursal.
- `GET  /audit/<uuid:id>/` → Detalle del evento (muestra `diff_json` y `meta_json`).

> Los endpoints son opcionales en MVP si solo se consulta por admin. Se recomiendan para soporte.

---

## 3) Contratos de entrada/salida (conceptual)

### Escritura de evento (API interna)

- **Input**:
  - `actor`: `request.user` o sistema.
  - `accion`: `create|update|delete|access`.
  - `tabla` y `fila_pk`: referencia al objeto (o `None` si es acceso general).
  - `diff_json`: JSON compacto (`{"campo": ["antes", "despues"], ...}` para update; o snapshot mínimo para create/delete).
  - `meta_json`: JSON con contexto (IP, path, método, empresa_id, sucursal_id, user_agent).
- **Proceso**: normaliza y persiste `AuditEvent`.
- **Output**: id de evento para posible correlación con logs técnicos.

### Acceso a vista sensible (middleware)

- **Input**: `request` a rutas marcadas (p.ej. `/ventas/<id>/`, `/pagos/`, `/comprobantes/`).
- **Proceso**: si cumple criterios, invoca `audit_log.write_event(accion="access", ...)`.
- **Output**: evento `access` registrado (no afecta respuesta).

### Mutaciones (signals)

- **Input**: `post_save` (`created=True/False`) y `post_delete` de modelos seleccionados.
- **Proceso**: construir `diff_json` comparando estado anterior/posterior (para update) o snapshot (create/delete).
- **Output**: evento `create|update|delete` persistido.

---

## 4) Integraciones y alcance

- **Modelos iniciales a auditar (MVP)**: `Venta`, `Pago`, `Comprobante`, `PrecioServicio`.
- **Campos sensibles**: montos, estado, referencias; no registrar datos altamente sensibles (en MVP no hay tarjetas).
- **Relación con `app_log`**: `AuditEvent` es **funcional**; `app_log` es **técnico**. Pueden correlacionarse por timestamps o IDs si se desea.

---

## 5) Seguridad

- Vistas `/audit/` requieren rol `admin` de la **empresa activa**.
- Sanitizar `meta_json` (no guardar cookies/headers sensibles).
- Limitar tamaño de `diff_json` para evitar payloads excesivos.

---

## 6) Roadmap inmediato

1. Modelo `AuditEvent` y migración.
2. Servicio `audit_log.write_event(...)`.
3. Hooks: conectar `post_save/post_delete` de 3–4 modelos clave.
4. Middleware de `access` para 1–2 rutas sensibles.
5. Listado/Detalle básico para inspección rápida en soporte.

# Módulo 14 — `apps/app_log` (Observabilidad: Logs Técnicos + Auditoría + Negocio)

> **Objetivo:** Proveer observabilidad **profesional y reutilizable**:
>
> - **Access logs** enriquecidos (HTTP) con `request_id` y `parent_request_id`.
> - **Business logs** (servicios de dominio) con `success`, `reason`, `affected_rows`, `prev_state/new_state`.
> - **Auditoría CRUD** automática con diffs `before/after`.
> - **Destino dual**: **BD** (consulta/soporte) y **archivos por usuario/día** (debug rápido).
> - **Sanitización de payloads** (body preview) y metadata útil para diagnóstico.

---

## 1) Estructura

```
apps/app_log/
├─ __init__.py
├─ apps.py                       # AppConfig que carga señales
├─ admin.py                      # Admin de AppLog y AuditLog
├─ migrations/
│  └─ __init__.py
├─ models.py                     # AppLog, AuditLog
├─ services/
│  ├─ __init__.py
│  └─ logger.py                  # log_event, log_exception, helpers
├─ logging_handler.py            # Handler: logging de Django → AppLog (BD)
├─ file_handler.py               # Handler: archivos por usuario/día
├─ logging_filters.py            # RequestContextFilter (usuario, empresa, req/parent IDs, etc.)
├─ signals.py                    # Auditoría CRUD (pre/post save/delete) + logger apps.audit
├─ selectors.py                  # Consultas de soporte (filtros por empresa, nivel, fecha)
├─ middleware.py                 # RequestID + AccessLog + ExceptionLog (enriquecidos)
├─ templates/
│  └─ app_log/
│     ├─ list.html               # Listado filtrable (opcional)
│     └─ detail.html             # Detalle (mensaje + meta_json)
└─ static/
   └─ app_log/
      ├─ app_log.css
      └─ app_log.js
```

---

## 2) Modelos

### `AppLog`

- **Qué registra:** eventos técnicos y **access logs** con contexto.
- **Campos clave:** `empresa_id`, `user_id`, `username`, `nivel`, `origen`, `evento`, `mensaje`, `http_method`, `http_path`, `http_status`, `duration_ms`, `ip`, `user_agent`, `meta_json`, `request_id`, `correlation_id`.
- **`meta_json` típico (access):**
  ```json
  {
    "status": 302,
    "duration_ms": 20,
    "route_name": "sales:cancel",
    "redirect_to": "/ventas/<id>/",
    "messages": [{ "level": "success", "message": "Venta cancelada." }],
    "template_name": null,
    "body_preview": { "csrfmiddlewaretoken": "***redacted***" },
    "parent_request_id": "aaa-bbb-ccc"
  }
  ```

### `AuditLog`

- **Qué registra:** auditoría de negocio (CRUD) con snapshots y diffs.
- **Campos clave:** `empresa_id`, `user_id`, `username`, `resource_type`, `resource_id`, `action (create|update|delete|soft_delete|restore)`, `changes`, `snapshot_before`, `snapshot_after`, `success`, `reason`, `ip`, `user_agent`, `request_id`.

---

## 3) Flujo de observabilidad

```mermaid
flowchart TD
    subgraph Request
        A[HTTP Request]
        B[RequestIDMiddleware]
        C[RequestLogMiddleware (access enriquecido)]
        D[Views/Services (business logs)]
        E[Signals (Audit CRUD)]
    end

    A --> B --> C --> D --> F
    D --> E --> F
    C --> F

    subgraph Sinks
        F[Handlers]
        F --> G[BD: AppLog / AuditLog]
        F --> H[Archivos: logs/YYYY-MM-DD/<username>.log]
    end
```

- **Correlación:** `request_id` por request; cuando hay redirect 3xx, el siguiente request lleva `parent_request_id` para encadenar POST → GET.

---

## 4) Dónde loguear (guía práctica)

- **Middleware (automático, una vez):**
  - Access log **enriquecido**: `method`, `path`, `status`, `duration_ms`, `redirect_to`, `route_name`, `template_name`, `messages`, `body_preview` (sanitizado).
  - Excepciones no manejadas → AppLog + archivos.
- **Servicios de dominio (`apps/*/services/*.py`):**
  - Cada operación crítica: **ANTES** (validaciones) y **DESPUÉS** (persistencia), con:
    - `success`, `reason`, `affected_rows`
    - `entity_id(s)`
    - `prev_state` / `new_state`
  - Ej: `cancelar_venta(venta, user, request)` hace `save(update_fields=["estado"])`, re-lee, compara y loguea `success`.
- **Señales (`signals.py`):**
  - CRUD automático con `changes` y snapshots (no para `bulk_*`).
- **Regla simple:** **vistas** llaman **servicios**; los servicios contienen la **verdad** (persistencia + logs de negocio).

---

## 5) Configuración en `settings.py`

### Variables

```python
AUDIT_TRACKED_MODELS = [
    "sales.Venta",
    "payments.Pago",
    "vehicles.Vehiculo",
    "catalog.Servicio",
]
AUDIT_EXCLUDE_FIELDS = ["id", "creado_en", "actualizado_en", "created_at", "updated_at"]
```

### Feature flags (por entorno)

```python
APP_LOG_ENABLE_DB = True              # BD AppLog
APP_LOG_ENABLE_AUDIT = True           # BD AuditLog (señales)
APP_LOG_ENABLE_FILES = True           # Archivos por usuario/día
APP_LOG_FILES_BASE_DIR = "logs"       # Carpeta de logs
# APP_LOG_JSON_FILES = False          # (opcional) JSONL si usás python-json-logger
```

### LOGGING (handlers y loggers)

- **Handlers**:
  - `applog_db`: a BD (AppLog).
  - `per_user_daily_file`: **formato corto** (negocio/auditoría).
  - `per_user_daily_access_file`: **formato extendido** (access).
- **Loggers**:
  - `apps.access` → `per_user_daily_access_file` (+ BD si flag).
  - `apps` → `per_user_daily_file` (+ BD si flag).
  - `apps.audit` → `per_user_daily_file` (+ BD si flag).
  - `django.request` (errores) → `per_user_daily_access_file` (+ BD si flag).

_(ver bloque de LOGGING en el settings del proyecto)_

---

## 6) Seguridad y sanitización

- **Nunca** almacenar secretos (contraseñas, tokens, cookies).
- `body_preview` captura **solo** primeras N bytes y **redacta** claves sensibles.
- Sanitizar snapshots y diffs (`AuditLog`) si contienen PII no necesaria.

---

## 7) Operación y retención

- **Archivos:** `logs/YYYY-MM-DD/<username>.log`.
- **BD:** AppLog/AuditLog consultables por admin (índices por fecha, empresa, status, path).
- **Retención recomendada:** dev 15–30 días (archivos), prod según normas (BD/archivos).
- Comando (sugerido) de limpieza BD: `manage.py prune_logs --days N` (implementar si aplica).

---

## 8) Debug checklist (casos como “cancelar venta”)

1. Ver access del **POST**: `status`, `messages`, `redirect_to`, `body_preview`.
2. Ver **business log** del servicio: `success`, `reason`, `prev_state/new_state`, `affected_rows`.
3. Ver **AuditLog**: `changes.estado` (debería mostrar `before → after`).
4. Si 2 o 3 no muestran cambio, es que **no se persistió** (revisar `save()` y `update_fields`).
5. Correlacionar POST `request_id` con GET `parent_request_id` para la pantalla resultante.

---

## 9) Buenas prácticas

- **Idempotencia** en servicios (si ya está cancelada, `success=False` con `reason` explícito).
- **Logs estructurados** (usa keys estables en `meta_json`).
- **No usar prints**; usar `logging.getLogger("apps")` y `log_event`.
- **Evitar bulk_update** en operaciones auditadas (no dispara señales); o loguear explícito.
- **Tests**: cubrir que el servicio deja `success=True` y que `AuditLog` registra el diff esperado.

---

# Módulo 15 — `apps/reporting` (Reportes Operativos)

> **Objetivo del módulo:** Centralizar reportes de **ventas, pagos, propinas y cierres de caja**, con filtros por rango de fechas, sucursal y cliente. Proveer vistas server-rendered y exportes CSV/Excel.  
> En MVP: reportes de lectura, sin edición ni cálculos complejos; todo basado en `selectors`.

---

## 1) Estructura de carpetas/archivos

```
apps/reporting/
├─ __init__.py
├─ apps.py                        # Config de la app (name="apps.reporting")
├─ urls.py                        # Rutas de reportes
├─ views.py                       # Vistas server-rendered (listados y exportes)
├─ selectors.py                   # Consultas optimizadas a sales/payments/cashbox
├─ services/
│  ├─ __init__.py
│  └─ exports.py                  # Generación de CSV/Excel con filtros aplicados
├─ templates/
│  └─ reporting/
│     ├─ sales_by_client.html     # Ventas agrupadas por cliente
│     ├─ payments_by_method.html  # Pagos agrupados por método y sucursal
│     ├─ tips.html                # Reporte de propinas
│     ├─ cash_closures.html       # Reporte de cierres de caja
│     └─ _filters.html            # Partial con formulario de filtros comunes
├─ static/
│  └─ reporting/
│     ├─ reporting.css            # Estilos propios (tablas, totales)
│     └─ reporting.js             # UX: datepickers, exportar con confirmación
└─ exports/
   └─ storage_backend.md          # Notas sobre dónde se guardan los exportes (MEDIA_ROOT/S3)
```

### Rol de cada componente

- **`selectors.py`**: consultas con `annotate`/`aggregate` sobre `sales.Venta`, `payments.Pago`, `cashbox.CierreCaja`.
- **`views.py`**: vistas que renderizan reportes con filtros (`fecha_desde`, `fecha_hasta`, `sucursal`, `cliente`).
- **`services/exports.py`**: utilidades para exportar datasets a CSV/Excel con nombres de columnas legibles.
- **`templates/reporting/*`**: UI de reportes con tablas, totales y botones “Exportar”.
- **`_filters.html`**: formulario reutilizable de filtros (fecha desde/hasta, sucursal, cliente).
- **`static/reporting/*`**: mejoras UX mínimas (datepickers, mensajes de feedback).

---

## 2) Endpoints propuestos

- `GET  /reportes/ventas-por-cliente/`  
  → listado de ventas agrupadas por cliente, con totales.

- `GET  /reportes/pagos-por-metodo/`  
  → pagos agrupados por método de pago × sucursal.

- `GET  /reportes/propinas/`  
  → totales de propinas por fecha/sucursal.

- `GET  /reportes/cierres-de-caja/`  
  → listado de cierres con resumen de totales.

- `GET  /reportes/export/<slug>/`  
  → exporte CSV/Excel del reporte solicitado (ej. `ventas-por-cliente`, `pagos-por-metodo`).

---

## 3) Contratos de entrada/salida (conceptual)

### Ventas por Cliente

- **Input (GET)**: `fecha_desde`, `fecha_hasta`, `sucursal?`, `cliente?`.
- **Proceso**: sumar `ventas.total` agrupando por cliente.
- **Output**: tabla `{cliente, cantidad_ventas, total}`.

### Pagos por Método

- **Input (GET)**: `fecha_desde`, `fecha_hasta`, `sucursal?`.
- **Proceso**: sumar `pagos.monto` agrupando por método × sucursal.
- **Output**: tabla `{sucursal, metodo, total}`.

### Propinas

- **Input (GET)**: `fecha_desde`, `fecha_hasta`, `sucursal?`.
- **Proceso**: sumar `pagos.propina` o campo equivalente.
- **Output**: tabla `{sucursal, fecha, propinas_total}`.

### Cierres de Caja

- **Input (GET)**: `fecha_desde`, `fecha_hasta`, `sucursal?`.
- **Proceso**: mostrar cierres de caja (abierto/cerrado, usuario, totales por método).
- **Output**: tabla `{cierre_id, sucursal, usuario, abierto_en, cerrado_en, totales}`.

---

## 4) Dependencias e integraciones

- **Depende de `sales`**: usa ventas para agrupar por cliente.
- **Depende de `payments`**: suma montos y propinas por método.
- **Depende de `cashbox`**: lista cierres y totales.
- **Depende de `org`**: filtro por sucursal/empresa.
- **Integración futura con `saas`**: limitar cantidad de exportes o accesos según plan.

---

## 5) Seguridad

- Solo usuarios autenticados.
- Validar **empresa activa** (tenancy).
- Filtrar sucursales: usuario debe tener `SucursalMembership` en esa sucursal.
- Exportes solo accesibles a roles `admin` / `auditor`.

---

## 6) Estado inicial del módulo

- `selectors` con consultas básicas para ventas, pagos, propinas y cierres.
- Vistas server-rendered con Bootstrap.
- Exportes CSV simples (Excel opcional).
- Plantillas con filtros de fechas y sucursal.
- Sidebar con menú “Reportes” → enlaces a cada reporte.

---

## 7) Roadmap inmediato

1. Implementar `selectors` optimizados.
2. Vistas y templates de los 4 reportes base.
3. Exportes CSV funcionales.
4. Integración con permisos de `SucursalMembership`.
5. Mejorar UX con filtros y datepickers.

---

## 8) Diagrama de relaciones (simplificado)

```mermaid
erDiagram
    Empresa ||--o{ Sucursal : contiene
    Empresa ||--o{ Cliente : tiene
    Cliente ||--o{ Venta : realiza
    Sucursal ||--o{ Venta : registra
    Venta ||--o{ Pago : incluye
    Sucursal ||--o{ CierreCaja : tiene
    CierreCaja ||--o{ CierreCajaTotal : resume

    Empresa {
        int id
        varchar nombre
    }

    Sucursal {
        int id
        varchar nombre
        int empresa_id
    }

    Cliente {
        int id
        varchar nombre
        int empresa_id
    }

    Venta {
        int id
        int cliente_id
        int sucursal_id
        decimal total
        date fecha
    }

    Pago {
        int id
        int venta_id
        varchar metodo
        decimal monto
        decimal propina
        date fecha
    }

    CierreCaja {
        int id
        int sucursal_id
        datetime abierto_en
        datetime cerrado_en
    }

    CierreCajaTotal {
        int id
        int cierre_id
        varchar medio
        decimal monto
        decimal propinas
    }
```
