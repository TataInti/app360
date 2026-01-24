# gunicorn.conf.py
import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, this can help with memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
loglevel = "info"
accesslog = "/Users/intipalaciofernandez/Library/CloudStorage/OneDrive-ActioBusinessPartners/-Software/app360/logs/access.log"
errorlog = "/Users/intipalaciofernandez/Library/CloudStorage/OneDrive-ActioBusinessPartners/-Software/app360/logs/error.log"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "app360"

# Server mechanics
daemon = False
pidfile = "/Users/intipalaciofernandez/Library/CloudStorage/OneDrive-ActioBusinessPartners/-Software/app360/logs/gunicorn.pid"
user = None
group = None
tmp_upload_dir = None

# SSL (handled by nginx)
keyfile = None
certfile = None

# Application
wsgi_module = "app:create_app"