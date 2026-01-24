# Roadmap de Desarrollo del Sistema de Gestión Administrativa Complementaria (SGAC)

## Introducción

Este documento presenta un roadmap detallado para el desarrollo del Sistema de Gestión Administrativa Complementaria (SGAC), un sistema web diseñado para la gestión financiera y administrativa de una distribuidora mayorista de carnes y embutidos. El SGAC integra datos de ventas y stock del ERP legacy vía archivos CSV, permitiendo la gestión de caja real, gastos, promociones, comisiones y reportes automáticos para la gerencia.

El proyecto está compuesto por un backend en Python Flask con SQLAlchemy y un frontend en React con Vite. Tras completar la refactorización de la arquitectura base, este roadmap se enfoca en implementar los módulos funcionales específicos requeridos por el cliente, incluyendo relaciones entre tablas y flujos de trabajo detallados.

## Estado Actual del Análisis

### Arquitectura General
- **Backend**: Aplicación Flask refactorizada con SQLAlchemy, organizada en blueprints para diferentes módulos (auth, compras, crm, ventas, rrhh, etc.)
- **Frontend**: Aplicación React con Vite, utilizando Axios para llamadas API, con componentes reutilizables y gestión de estado global
- **Base de Datos**: PostgreSQL en desarrollo y producción
- **Autenticación**: Sistema basado en roles con acceso controlado por módulos
- **Infraestructura**: Docker, CI/CD con GitHub Actions, tests automatizados, documentación completa

### Problemas Identificados y Requerimientos Pendientes

#### Funcionalidades Específicas del SGAC
- **Falta de Integración con ERP Legacy**: No existe mecanismo para importar archivos CSV de ventas y stock
- **Gestión de Caja Real**: Ausencia de registro de ingresos/egresos por múltiples instrumentos de pago
- **Conciliación Diaria**: No se diferencia ingresos reales versus ventas declaradas
- **Promociones y Simuladores**: Sin sistema para crear promociones y simular impacto en rentabilidad
- **Comisiones**: Falta liquidación automática de comisiones por vendedores
- **Gestión de Gastos**: No hay registro de egresos por categoría ni agenda de vencimientos
- **Recursos Humanos**: Ausencia de gestión de turnos, asistencia y adelantos
- **Business Intelligence**: Sin tablero de KPIs ni reportes automáticos por email

#### Relaciones y Flujos de Trabajo
- **Relaciones entre Tablas**: Necesidad de definir y implementar esquemas de relaciones entre Usuario, Venta, MovimientoCaja, Promocion, Gasto, Turno, etc.
- **Flujos de Trabajo**: Integración de procesos como importación CSV → registro ventas → conciliación caja → liquidación comisiones → reportes BI

## Roadmap de Desarrollo

### Fase 7: Desarrollo del Módulo de Ventas Integrado (2-3 semanas)
**Prioridad: Alta**

#### Tareas
1. **Implementación de Importación CSV**
   - Crear endpoint `/ventas/importar` (POST) para carga y procesamiento de archivos CSV
   - Homologar columnas relevantes (fecha, producto, cantidad, precio, cliente)
   - Validar y procesar datos, diferenciando precio efectivo vs. precio contrato

2. **Gestión de Ventas Reales**
   - Crear modelos para Venta, Cliente, Producto con relaciones apropiadas
   - Implementar endpoints para listar ventas filtradas (`/ventas/listar`)
   - Agregar funcionalidad de exportación a Excel (`/ventas/exportar`)

3. **Relaciones de Datos**
   - Venta *---1 Cliente
   - Venta *---1 Producto
   - Implementar constraints y validaciones en modelos

#### Flujo de Trabajo
1. Usuario sube archivo CSV → Validación → Procesamiento → Almacenamiento en BD
2. Visualización de historial con filtros → Exportación a Excel

#### Criterios de Éxito
- Importación exitosa de archivos CSV de ejemplo
- Listado y filtrado de ventas funcionando
- Exportación a Excel operativa

### Fase 8: Desarrollo del Módulo de Tesorería Multicanal (3-4 semanas)
**Prioridad: Alta**

#### Tareas
1. **Registro de Ingresos y Egresos**
   - Crear modelos MovimientoCaja, InstrumentoPago, ArqueoCaja
   - Implementar endpoints `/tesoreria/ingresos` y `/tesoreria/egresos`
   - Soporte para múltiples instrumentos: efectivo, cheques, tarjetas, transferencias

2. **Conciliación y Arqueos**
   - Endpoint `/tesoreria/arqueo` para arqueos diarios y por turno
   - Lógica de conciliación: ingresos reales vs. ventas declaradas
   - Control de saldos por instrumento al cierre del día

3. **Exportación de Estado de Caja**
   - Endpoint `/tesoreria/exportar` con filtros por fechas, usuario, instrumento
   - Generación de reportes en Excel

#### Relaciones de Datos
- Usuario 1---* MovimientoCaja
- MovimientoCaja *---1 InstrumentoPago
- MovimientoCaja *---1 ArqueoCaja

#### Flujo de Trabajo
1. Registro de movimientos → Arqueo diario → Conciliación automática → Exportación de estado

#### Criterios de Éxito
- Registro completo de movimientos por instrumento
- Arqueos y conciliación funcionando
- Exportación de reportes operativa

### Fase 9: Desarrollo del Módulo de Estrategia Comercial y Simuladores (3-4 semanas)
**Prioridad: Media-Alta**

#### Tareas
1. **Gestión de Promociones**
   - Crear modelo Promocion con reglas de aplicación
   - Endpoint `/comercial/promociones` para CRUD de promociones
   - Soporte para descuentos, combos, liquidación de stock

2. **Simulador de Rentabilidad**
   - Endpoint `/comercial/simulador` para proyección de impacto
   - Cálculos de margen neto antes de aplicar promociones
   - Exportación de resultados a Excel

3. **Liquidación de Comisiones**
   - Modelo Comision vinculado a Usuario
   - Endpoint `/comercial/comisiones` para liquidación por criterios
   - Cálculos basados en ventas cobradas, margen por producto

#### Relaciones de Datos
- Promocion *---* Producto
- Venta 1---* PromocionAplicada
- Comision 1---1 Usuario

#### Flujo de Trabajo
1. Creación de promociones → Simulación de impacto → Aplicación → Liquidación de comisiones

#### Criterios de Éxito
- Promociones configurables y aplicables
- Simulador funcional con proyecciones precisas
- Comisiones liquidadas correctamente

### Fase 10: Desarrollo del Módulo de Gestión de Gastos e Impuestos (2-3 semanas)
**Prioridad: Media-Alta**

#### Tareas
1. **Registro de Gastos**
   - Crear modelos Gasto, CategoriaGasto, Proveedor
   - Endpoint `/gastos/registrar` para alta de gastos
   - Categorías: logística, energía, servicios, mantenimiento, impuestos

2. **Agenda de Vencimientos**
   - Sistema de recordatorios para pagos a proveedores
   - Control de retiros de socios y pagos especiales

3. **Exportación de Gastos**
   - Endpoint `/gastos/exportar` con filtros por fechas, categoría, proveedor
   - Generación de listados en Excel

#### Relaciones de Datos
- Gasto *---1 CategoriaGasto
- Gasto *---1 Proveedor

#### Flujo de Trabajo
1. Registro de gastos → Agenda de vencimientos → Exportación de reportes

#### Criterios de Éxito
- Gastos registrados por categoría
- Agenda de vencimientos operativa
- Exportación de listados funcional

### Fase 11: Desarrollo del Módulo de Recursos Humanos y Turnos (2-3 semanas)
**Prioridad: Media**

#### Tareas
1. **Gestión de Cuadrantes y Turnos**
   - Crear modelo Turno vinculado a Usuario
   - Endpoint `/rrhh/turnos` para gestión de cuadrantes

2. **Registro de Asistencia**
   - Modelo Asistencia relacionado con Turno
   - Endpoint `/rrhh/asistencia` para registro y consulta
   - Control de novedades: inasistencias, llegadas tarde

3. **Adelantos y Pagos**
   - Vinculación de adelantos con estado de caja
   - Endpoint `/rrhh/exportar` para exportación de novedades

#### Relaciones de Datos
- Turno *---1 Usuario
- Asistencia *---1 Turno

#### Flujo de Trabajo
1. Definición de turnos → Registro de asistencia → Control de novedades → Exportación

#### Criterios de Éxito
- Cuadrantes gestionados
- Asistencia registrada
- Novedades exportables

### Fase 12: Desarrollo del Módulo de Business Intelligence y Reportes (3-4 semanas)
**Prioridad: Media-Alta**

#### Tareas
1. **Tablero de KPIs**
   - Endpoint `/bi/dashboard` con métricas principales
   - KPIs: ventas reales, margen neto, gastos, comisiones, saldo de caja

2. **Análisis y Rankings**
   - Endpoint `/bi/ranking` para análisis por productos y clientes

3. **Reportes Automáticos**
   - Endpoint `/reportes/resumen-diario` para generación automática
   - Envío por email a las 21:30hs (`/reportes/email-diario`)
   - Exportación manual de vistas a Excel

#### Flujo de Trabajo
1. Recopilación de datos → Cálculo de KPIs → Generación de resumen diario → Envío automático por email

#### Criterios de Éxito
- Tablero BI operativo con KPIs actualizados
- Rankings y análisis disponibles
- Reportes diarios enviados automáticamente

### Fase 13: Integración Final y Testing (2-3 semanas)
**Prioridad: Alta**

#### Tareas
1. **Integración de Módulos**
   - Verificar flujos de trabajo entre módulos (e.g., ventas → tesorería → BI)
   - Asegurar consistencia de datos entre relaciones

2. **Testing Completo**
   - Tests de integración para flujos completos
   - Validación de exportaciones Excel
   - Testing de seguridad y roles

3. **Optimización y Documentación**
   - Actualizar documentación con nuevos endpoints
   - Optimizar consultas para reportes BI

#### Criterios de Éxito
- Todos los módulos integrados y funcionales
- Flujos de trabajo completos probados
- Documentación actualizada

## Esquema de Relaciones entre Tablas

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

## Flujos de Trabajo Principales

### Flujo de Ventas y Conciliación
1. Importación CSV de ERP → Procesamiento de ventas reales
2. Registro de ingresos en Tesorería → Conciliación diaria
3. Aplicación de promociones → Cálculo de comisiones
4. Generación de reportes BI → Envío automático por email

### Flujo de Gastos y RRHH
1. Registro de gastos → Agenda de vencimientos
2. Gestión de turnos → Registro de asistencia
3. Control de adelantos → Vinculación con caja

### Flujo de Reportes
1. Recopilación automática de datos → Cálculo de KPIs
2. Generación de resumen diario → Envío por email
3. Exportaciones manuales por usuario según permisos

## Métricas de Éxito Globales

- **Funcionalidades Implementadas**: 100% de módulos requeridos operativos
- **Integración ERP**: Importación CSV exitosa y validada
- **Conciliación Diaria**: Automatizada con precisión del 100%
- **Reportes Automáticos**: Envío diario a las 21:30hs sin fallos
- **Cobertura de Tests**: > 90% incluyendo nuevos módulos
- **Tiempo de Respuesta**: < 2s para consultas principales
- **Disponibilidad**: 99.9% uptime en producción

## Riesgos y Mitigaciones

- **Riesgo**: Errores en importación CSV afectan integridad de datos
  - **Mitigación**: Validaciones exhaustivas y rollback en caso de error

- **Riesgo**: Conciliación manual sobrecarga operativa
  - **Mitigación**: Automatización completa con alertas de discrepancias

- **Riesgo**: Dependencias entre módulos causan bloqueos
  - **Mitigación**: Desarrollo incremental con integración continua

- **Riesgo**: Volumen de datos afecta rendimiento de reportes
  - **Mitigación**: Optimización de consultas e índices en BD

## Próximos Pasos

1. Obtener aprobación del roadmap actualizado
2. Asignar recursos y timeline específico por fase
3. Comenzar con Fase 7: Desarrollo del Módulo de Ventas Integrado
4. Establecer métricas de seguimiento semanal y revisiones de integración

Este roadmap proporciona una ruta clara para implementar el SGAC completo, alineado con los requerimientos del cliente y aprovechando la arquitectura refactorizada existente.