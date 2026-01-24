# Requerimientos de Módulos - Sistema de Gestión Administrativa Complementaria (SGAC)

Fecha: 24/01/2026  
Preparado por: TataInti

## 1. Descripción General

El SGAC es un sistema complementario para la gestión financiera y administrativa de una distribuidora mayorista de carnes y embutidos. Debe integrar los datos de ventas y stock del ERP legacy vía archivos CSV, permitiendo la gestión de caja real, gastos, promociones, comisiones y reportes automáticos para la gerencia.

---

## 2. Módulos y Requerimientos Funcionales

---

### 2.1. Módulo de Ventas Integrado

- Importar archivos CSV provenientes del ERP legacy, homologando columnas relevantes (fecha, producto, cantidad, precio, cliente).
- Registrar la venta real (precio efectivo) diferenciada del precio vendido por contrato.
- Visualizar historial de ventas por filtro de fechas, producto y cliente.
- Generar reportes exportables en Excel (.xlsx) de ventas filtradas.

---

### 2.2. Módulo de Tesorería Multicanal

- Registrar ingresos y egresos por múltiples instrumentos: efectivo, cheques propios y de terceros, tarjetas, posnet, transferencias.
- Gestionar arqueos de caja diarios y por turno.
- Conciliación diaria: diferenciar ingresos reales versus ventas declaradas.
- Permitir exportar estado de caja (filtrado por fechas, usuario, tipo de instrumento) en Excel (.xlsx).
- Control de saldos por instrumento al cierre del día.

---

### 2.3. Módulo de Estrategia Comercial y Simuladores

- Crear y gestionar promociones: descuentos, combos, liquidación de stock cercano a vencimiento.
- Configurar reglas de aplicación de promociones por producto, cliente o volumen.
- Simulador de rentabilidad: proyectar el impacto de promociones sobre el margen neto antes de aplicar.
- Liquidar comisiones para vendedores según criterio definido (ventas cobradas, margen por producto, cumplimientos).
- Exportar resultados del simulador a Excel.

---

### 2.4. Módulo de Gestión de Gastos e Impuestos

- Registrar egresos por categoría (logística, energía, servicios, mantenimiento, impuestos).
- Agenda de vencimientos y pagos a proveedores no integrados al ERP legacy.
- Control de retiros de socios y pagos especiales.
- Exportar listados de gastos filtrados por fechas, categoría y proveedor en Excel.

---

### 2.5. Módulo de Recursos Humanos y Turnos

- Gestión de cuadrantes y turnos del personal administrativo y operativo.
- Registro de asistencia, novedades (inasistencias, llegadas tarde), adelantos de sueldo y pagos.
- Vincular pagos o adelantos directamente con el estado de caja en Tesorería.
- Exportar cuadrantes y novedades a Excel.

---

### 2.6. Módulo de Business Intelligence (BI) y Reportes Automáticos

- Tablero con KPIs principales: ventas reales, margen neto, gastos, comisiones, saldo de caja.
- Ranking y análisis por productos y clientes.
- Generar automáticamente un resumen diario de actividad y saldo de caja a las 21:30hs.
- Enviar el resumen diario vía email a gerentes y administradores.
- Permitir la exportación manual de cualquier vista a Excel (.xlsx).

---

## 3. Requerimientos Técnicos Transversales

- Stack sugerido: Frontend en HTML5/CSS/JS, Backend Node.js + Python, Base de datos PostgreSQL, alojamiento en VPS.
- Seguridad: acceso por usuarios con roles (admin, gerente), registro de logs de exportación.
- Backups automáticos diarios.
- Panel de configuración de empresa, definición de usuarios y permisos.

---

## 4. Esquema de Rutas y Relaciones entre Tablas y Módulos

### 4.1. Esquema de rutas (API RESTful)

- **/ventas/importar** (POST): Carga de archivo CSV y procesamiento de ventas reales.
- **/ventas/listar** (GET): Listado filtrado de ventas (por fecha, cliente, producto).
- **/ventas/exportar** (GET): Descarga de ventas en Excel.
- **/tesoreria/ingresos** (GET/POST): Ingresos por instrumento de pago.
- **/tesoreria/egresos** (GET/POST): Registro de egresos.
- **/tesoreria/arqueo** (GET/POST): Arqueos diarios y por turno.
- **/tesoreria/exportar** (GET): Descarga de estado de caja en Excel.
- **/comercial/promociones** (GET/POST): Gestión de promociones.
- **/comercial/simulador** (POST): Simulación de impacto en rentabilidad.
- **/comercial/comisiones** (GET/POST): Liquidación y exportación de comisiones.
- **/gastos/listar** (GET): Lista de gastos por categoría/fecha.
- **/gastos/registrar** (POST): Alta de gasto.
- **/gastos/exportar** (GET): Descarga de gastos en Excel.
- **/rrhh/turnos** (GET/POST): Gestión de cuadrantes.
- **/rrhh/asistencia** (GET/POST): Registro y consulta de asistencia.
- **/rrhh/exportar** (GET): Exportación de novedades RRHH.
- **/bi/dashboard** (GET): Tablero BI y KPIs.
- **/bi/ranking** (GET): Ranking de clientes/productos.
- **/reportes/resumen-diario** (GET): Genera el resumen de actividad diario.
- **/reportes/email-diario** (POST): Envío automático por email a las 21:30hs.

### 4.2. Relaciones entre tablas principales (Esquema simplificado)

```
[Usuario] 1---* [MovimientoCaja]
                 \
                  *---1 [ArqueoCaja]
                  *---1 [InstrumentoPago]
[Venta] *---1 [Cliente]
[Venta] *---1 [Producto]
[Venta] 1---* [PromocionAplicada]
[Promocion] *---* [Producto]
[Gasto] *---1 [CategoriaGasto]
[Gasto] *---1 [Proveedor]
[Turno] *---1 [Usuario]
[Asistencia] *---1 [Turno]
[Comision] 1---1 [Usuario]
```

- Una venta se vincula a un cliente y a uno o varios productos.
- Un movimiento de caja registra ingresos/egresos, la relación con usuario/admin, y el tipo de instrumento.
- Los arqueos de caja se relacionan con usuario y resumen de movimientos.
- Los egresos tienen categoría y proveedor.
- Los turnos y asistencia se vinculan al usuario (personal).
- Las promociones aplicadas se relacionan con las ventas y productos involucrados.
- Las comisiones se liquidan por usuario y período.

---

## 5. Restricciones

- No debe gestionar facturación ni stock (esas funciones son exclusivas del ERP legacy).
- Debe integrarse por archivos CSV, sin necesidad de conexión directa al ERP.
- La visibilidad de exportación de datos debe estar limitada por rol de usuario.

---

## 6. Consideraciones Finales

- Toda función exportable debe respetar los filtros visuales activos en la pantalla.
- El sistema debe ser extensible para futuros módulos o integración APIs.
- Documentación técnica y manual de usuario final como entregable obligatorio.