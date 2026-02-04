# Despliegue de Mejoras de Tesorería - App360

## Resumen de Cambios

Se han implementado las siguientes mejoras en el módulo de Tesorería:

### 1. Catálogo de Destinos de Arqueos
- Nuevo modelo `DestinoArqueo` para gestionar destinos del dinero
- 8 destinos predefinidos: Banco, Caja Fuerte, Caja General, Tesoro Central, Cambio de Turno, Transporte de Valores, Caja Chica, Otro
- Administrable desde el panel de admin en `/admin`

### 2. Sistema de Auditoría para Arqueos
- Nuevo modelo `LogArqueo` para registro completo de ediciones
- Solo administradores pueden editar arqueos
- Solo se pueden editar arqueos del día actual
- Justificación obligatoria para cada edición
- Historial completo de cambios visible en la interfaz

### 3. Nuevos Instrumentos de Pago
Se agregaron 16 nuevos instrumentos:
- Flor, Lacteos, Friar, Financiera
- Banco Galicia, Banco Macro
- Tarjetas cupones
- Efectivo Friar, Efectivo Lacteos
- Cheques propios, Cheques clientes, Cheques financiera
- Echeq
- Diferencia Presup/Vta
- Intereses, Comisiones

---

## Archivos Modificados

### Backend
- `models/tesoreria.py` - Nuevos modelos DestinoArqueo, LogArqueo, campos adicionales en ArqueoCaja
- `blueprints/admin.py` - Configuración de administración de destinos
- `blueprints/tesoreria.py` - Endpoints: GET destinos, PUT arqueos, GET arqueos/logs
- `migrations/versions/add_destinos_arqueo_and_logs.py` - Migración con seeds

### Frontend
- `templates/tesoreria_arqueos.html` - Modal de edición, dropdown de destinos, historial de cambios

---

## Instrucciones de Despliegue en VPS

### Paso 1: Conectar al VPS
```bash
ssh usuario@servidor-ip
cd /ruta/al/proyecto/app360
```

### Paso 2: Hacer Backup de la Base de Datos (IMPORTANTE)
```bash
# Backup de PostgreSQL
pg_dump -U app360 app360 > backup_antes_migracion_$(date +%Y%m%d_%H%M%S).sql

# Verificar que el backup existe
ls -lh backup_*.sql
```

### Paso 3: Actualizar Código desde Git
```bash
# Asegurarse de estar en la rama correcta
git status
git pull origin main  # o la rama correspondiente
```

### Paso 4: Ejecutar la Migración
```bash
# Opción A: Usar el script automatizado
bash scripts/migrate_tesoreria.sh

# Opción B: Ejecutar manualmente
source venv/bin/activate
python -m flask db upgrade
```

### Paso 5: Verificar la Migración
```bash
# Conectar a PostgreSQL y verificar las tablas nuevas
psql -U app360 app360

# Dentro de psql:
\dt destinos_arqueo
\dt logs_arqueo
\d arqueos_caja
SELECT * FROM destinos_arqueo;
SELECT * FROM instrumentos_pago WHERE nombre IN ('Flor', 'Lacteos', 'Friar');
\q
```

### Paso 6: Reiniciar el Servicio
```bash
# Si usas systemd
sudo systemctl restart app360
sudo systemctl status app360

# Si usas gunicorn directo
pkill -HUP gunicorn
```

### Paso 7: Verificar en el Navegador
1. Acceder a `https://app360.actioconsultores.com/admin`
2. Verificar que aparezca "Destinos de Arqueo" en el panel de administración
3. Acceder a Tesorería → Arqueos
4. Crear un nuevo arqueo y verificar el dropdown de destinos
5. Editar un arqueo del día actual (solo como admin) y verificar el historial

---

## Rollback en Caso de Problemas

Si algo sale mal:

```bash
# Opción 1: Revertir migración
python -m flask db downgrade

# Opción 2: Restaurar backup
psql -U app360 app360 < backup_antes_migracion_YYYYMMDD_HHMMSS.sql

# Opción 3: Revertir código
git log --oneline  # Ver commits
git revert HEAD    # Revertir último commit
```

---

## Pruebas Post-Despliegue

### Caso de Prueba 1: Crear Arqueo con Destino
1. Login como usuario de tesorería
2. Ir a Tesorería → Arqueos → Nuevo Arqueo
3. Completar datos y seleccionar "Banco" como destino
4. Guardar y verificar que aparece en la tabla

### Caso de Prueba 2: Editar Arqueo (Admin)
1. Login como administrador
2. Ir a Tesorería → Arqueos
3. Hacer clic en el botón "Editar" de un arqueo del día actual
4. Modificar el saldo final
5. Escribir justificación: "Corrección por error de conteo"
6. Guardar y verificar que se recalcula la diferencia

### Caso de Prueba 3: Ver Historial de Ediciones
1. En la tabla de arqueos, hacer clic en el icono de reloj del arqueo editado
2. Verificar que muestra la fecha/hora, usuario, justificación y cambios realizados

### Caso de Prueba 4: Restricciones de Seguridad
1. Intentar editar un arqueo de ayer (debe mostrar error)
2. Login como usuario no-admin (debe no ver botón de editar)
3. Intentar editar sin justificación (debe mostrar error)

### Caso de Prueba 5: Nuevos Instrumentos de Pago
1. Ir a Admin → Instrumentos de Pago
2. Verificar que aparecen los 16 nuevos instrumentos
3. Crear un movimiento usando "Banco Galicia"

---

## Monitoreo Post-Despliegue

```bash
# Ver logs en tiempo real
tail -f logs/app.log

# Buscar errores
grep -i error logs/app.log

# Ver logs de PostgreSQL
sudo tail -f /var/log/postgresql/postgresql-*.log
```

---

## Contacto

En caso de problemas durante el despliegue, revisar:
- `logs/app.log` - Errores de la aplicación
- `logs/security.log` - Eventos de seguridad
- Output del script de migración

---

## Checklist de Despliegue

- [ ] Backup de base de datos realizado
- [ ] Código actualizado desde Git
- [ ] Migración ejecutada sin errores
- [ ] Tablas verificadas en PostgreSQL
- [ ] Servicio reiniciado correctamente
- [ ] Interfaz accesible en navegador
- [ ] Prueba de crear arqueo con destino
- [ ] Prueba de editar arqueo (admin)
- [ ] Prueba de ver historial
- [ ] Instrumentos de pago verificados
- [ ] Logs monitoreados sin errores críticos
