# Backlog de mejoras

Prioridad alta a baja. Cada item incluye alcance y resultado esperado.

## P0 (seguridad y estabilidad inmediata)

- P0.1 Endurecer autenticacion en API REST: `jwt_required` en POST/PUT/DELETE, excepciones documentadas. Resultado: operaciones mutativas solo autenticadas.
- P0.2 Unificar rate limiting con configuracion real (usar `RATELIMIT_STORAGE_URL` y `RATELIMIT_DEFAULT`). Resultado: limites consistentes y compatibles con multi-worker.
- P0.3 Estandarizar errores: respuestas genericas al cliente + logging interno con trazas. Resultado: menos leakage de informacion y debugging mas claro.
- P0.4 Resolver import circular en `login()` (remover import no usado de `limiter`). Resultado: menor riesgo de fallos de arranque.

## P1 (calidad y confiabilidad)

- P1.1 Validacion de payloads y mensajes 400 detallados por campo faltante. Resultado: menos 500 por `KeyError`.
- P1.2 Manejo robusto de fechas ISO con errores 400. Resultado: datos coherentes y menos fallos en parsing.
- P1.3 Revisar handlers de logging para evitar duplicados en reinicios/tests. Resultado: logs limpios.

## P2 (rendimiento y escalabilidad)

- P2.1 Eliminar N+1 en endpoints con relaciones (eager loading). Resultado: menor latencia en listas grandes.
- P2.2 Paginacion por defecto en listados (`products`, `leads`, `stock`, etc.). Resultado: respuesta estable en BD grandes.
- P2.3 Indices en campos con filtros frecuentes (segun modelos). Resultado: consultas mas rapidas.

## P3 (configuracion y operacion)

- P3.1 Mover validaciones de env (`SECRET_KEY`, `ADMIN_PASSWORD`) a `create_app()` con mensajes claros. Resultado: menos bloqueos en migraciones/scripts.
- P3.2 Revisar CSP y cookies seguras segun uso real de frontend. Resultado: seguridad sin romper funcionalidades.
- P3.3 Documentar variables necesarias en README. Resultado: onboarding mas rapido.

## P4 (tests y verificacion)

- P4.1 Tests de auth para endpoints mutativos (con y sin JWT). Resultado: cobertura minima de seguridad.
- P4.2 Tests basicos de rate limiting si aplica. Resultado: garantias en limites.
