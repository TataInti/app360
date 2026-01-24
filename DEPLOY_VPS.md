# 🚀 Guía de Despliegue en VPS - App360

## Requisitos Previos del VPS

- **Ubuntu 22.04 LTS** o superior
- **Python 3.12+**
- **PostgreSQL 14+**
- **Redis 7+**
- **Nginx**
- **Git**

---

## Paso 1: Preparar el Servidor

```bash
# Conectarse al VPS
ssh usuario@tu-vps-ip

# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependencias del sistema
sudo apt install -y python3.12 python3.12-venv python3-pip \
    postgresql postgresql-contrib \
    redis-server \
    nginx \
    git \
    certbot python3-certbot-nginx
```

---

## Paso 2: Configurar PostgreSQL

```bash
# Acceder a PostgreSQL
sudo -u postgres psql

# Crear usuario y base de datos (en el prompt de psql)
CREATE USER app360 WITH PASSWORD 'tu_password_seguro';
CREATE DATABASE app360 OWNER app360;
GRANT ALL PRIVILEGES ON DATABASE app360 TO app360;
\q

# Verificar conexión
psql -U app360 -d app360 -h localhost
```

---

## Paso 3: Configurar Redis

```bash
# Verificar que Redis esté corriendo
sudo systemctl status redis

# Si no está activo
sudo systemctl start redis
sudo systemctl enable redis

# Verificar funcionamiento
redis-cli ping
# Debe responder: PONG
```

---

## Paso 4: Clonar el Repositorio

```bash
# Crear directorio para la aplicación
sudo mkdir -p /var/www/app360
sudo chown $USER:$USER /var/www/app360

# Clonar repositorio
cd /var/www
git clone https://github.com/tu-usuario/app360.git app360
cd app360
```

---

## Paso 5: Configurar Variables de Entorno

```bash
# Copiar plantilla de configuración
cp .env.example .env

# Editar con tus valores de producción
nano .env
```

**Contenido del archivo `.env`:**
```env
# Seguridad (GENERAR VALORES ÚNICOS)
SECRET_KEY=tu_clave_secreta_muy_larga_y_aleatoria
JWT_SECRET_KEY=otra_clave_secreta_diferente
ADMIN_PASSWORD=password_admin_seguro

# Base de datos PostgreSQL
DATABASE_URL=postgresql://app360:tu_password_seguro@localhost:5432/app360

# Redis para rate limiting
REDIS_URL=redis://localhost:6379/0
RATELIMIT_ENABLED=true

# Seguridad CSRF
WTF_CSRF_ENABLED=true
WTF_CSRF_TIME_LIMIT=3600

# Producción
FLASK_ENV=production
SESSION_COOKIE_SECURE=true
REMEMBER_COOKIE_SECURE=true
```

**Generar claves seguras:**
```bash
# Generar SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generar JWT_SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Paso 6: Ejecutar Script de Despliegue

```bash
# Dar permisos de ejecución
chmod +x scripts/deploy.sh

# Ejecutar el script
./scripts/deploy.sh
```

El script automáticamente:
- ✅ Crea entorno virtual
- ✅ Instala dependencias
- ✅ Verifica configuración
- ✅ Crea directorios necesarios
- ✅ Verifica conexión a PostgreSQL
- ✅ Ejecuta migraciones
- ✅ Verifica que la aplicación funciona

---

## Paso 7: Configurar Servicio Systemd

```bash
# Copiar archivo de servicio
sudo cp scripts/app360.service /etc/systemd/system/

# Editar si es necesario (cambiar usuario)
sudo nano /etc/systemd/system/app360.service

# Recargar systemd
sudo systemctl daemon-reload

# Habilitar servicio
sudo systemctl enable app360

# Iniciar servicio
sudo systemctl start app360

# Verificar estado
sudo systemctl status app360
```

---

## Paso 8: Configurar Nginx

```bash
# Copiar configuración de nginx
sudo cp scripts/nginx-app360.conf /etc/nginx/sites-available/app360

# Editar el dominio
sudo nano /etc/nginx/sites-available/app360
# Cambiar 'tu-dominio.com' por tu dominio real

# Habilitar sitio
sudo ln -s /etc/nginx/sites-available/app360 /etc/nginx/sites-enabled/

# Verificar configuración
sudo nginx -t

# Recargar nginx
sudo systemctl reload nginx
```

---

## Paso 9: Configurar SSL con Let's Encrypt

```bash
# Obtener certificado SSL
sudo certbot --nginx -d tu-dominio.com -d www.tu-dominio.com

# Verificar renovación automática
sudo certbot renew --dry-run
```

---

## Paso 10: Verificar Despliegue

```bash
# Verificar servicios
sudo systemctl status app360
sudo systemctl status nginx
sudo systemctl status postgresql
sudo systemctl status redis

# Verificar logs
tail -f /var/www/app360/logs/app.log
tail -f /var/www/app360/logs/security.log

# Probar endpoint de salud
curl http://localhost:5000/api/health

# Probar desde internet
curl https://tu-dominio.com/api/health
```

---

## Comandos Útiles de Mantenimiento

### Reiniciar la Aplicación
```bash
sudo systemctl restart app360
```

### Ver Logs en Tiempo Real
```bash
# Logs de la aplicación
tail -f /var/www/app360/logs/app.log

# Logs de seguridad
tail -f /var/www/app360/logs/security.log

# Logs de systemd
sudo journalctl -u app360 -f
```

### Actualizar la Aplicación
```bash
cd /var/www/app360

# Obtener últimos cambios
git pull origin main

# Activar entorno virtual
source venv/bin/activate

# Actualizar dependencias
pip install -r requirements.txt

# Ejecutar migraciones
flask db upgrade

# Reiniciar servicio
sudo systemctl restart app360
```

### Backup de Base de Datos
```bash
# Crear backup
pg_dump -U app360 -h localhost app360 > backup_$(date +%Y%m%d).sql

# Restaurar backup
psql -U app360 -h localhost app360 < backup_20260124.sql
```

---

## Solución de Problemas

### Error: "Connection refused" en PostgreSQL
```bash
# Verificar que PostgreSQL esté corriendo
sudo systemctl status postgresql

# Verificar configuración de conexión
sudo nano /etc/postgresql/14/main/pg_hba.conf
# Asegurar que existe: local all app360 md5
sudo systemctl restart postgresql
```

### Error: "Redis connection failed"
```bash
# Verificar Redis
sudo systemctl status redis
redis-cli ping

# Reiniciar Redis
sudo systemctl restart redis
```

### Error 502 Bad Gateway en Nginx
```bash
# Verificar que app360 esté corriendo
sudo systemctl status app360

# Ver logs de error
sudo journalctl -u app360 --no-pager -n 50

# Reiniciar ambos servicios
sudo systemctl restart app360
sudo systemctl restart nginx
```

### Verificar Permisos
```bash
# El usuario que corre app360 debe tener permisos en /var/www/app360
sudo chown -R www-data:www-data /var/www/app360
sudo chmod -R 755 /var/www/app360
```

---

## Checklist de Seguridad Post-Despliegue

- [ ] SECRET_KEY y JWT_SECRET_KEY son únicos y seguros
- [ ] ADMIN_PASSWORD es fuerte (mínimo 12 caracteres)
- [ ] SSL/HTTPS está habilitado
- [ ] Firewall configurado (solo puertos 22, 80, 443)
- [ ] Fail2ban instalado para protección SSH
- [ ] Backups automáticos configurados
- [ ] Monitoreo de logs habilitado
- [ ] Rate limiting funcionando (verificar en logs de seguridad)

---

## Arquitectura Final

```
Internet
    │
    ▼
┌─────────────────┐
│     Nginx       │ (Reverse proxy + SSL)
│   :80 / :443    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Gunicorn     │ (WSGI Server)
│  127.0.0.1:5000 │
│   4 workers     │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐  ┌───────┐
│ Redis │  │ Postgr│
│ :6379 │  │ :5432 │
└───────┘  └───────┘
```
