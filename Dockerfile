# Dockerfile para App360
FROM python:3.12-slim

# Establecer directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de dependencias
COPY requirements.txt .
COPY pyproject.toml .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY . .

# Crear directorio para base de datos
RUN mkdir -p instance

# Variables de entorno - valores seguros deben pasarse en runtime
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
# SECRET_KEY y ADMIN_PASSWORD deben configurarse via docker-compose o variables de entorno
# NO definir valores por defecto aquí por seguridad

# Puerto
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Usar gunicorn para producción (más seguro y eficiente que app.run())
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "30", "app:create_app()"]