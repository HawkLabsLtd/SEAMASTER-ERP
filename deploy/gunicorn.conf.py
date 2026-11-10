import multiprocessing
import os

# Server socket
bind = "127.0.0.1:8000"

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
threads = 2

# Timeouts
timeout = 120
keepalive = 5

# Logging
accesslog = "/var/log/seamaster/access.log"
errorlog = "/var/log/seamaster/error.log"
loglevel = "info"
capture_output = True

# Process naming
proc_name = "seamaster-gunicorn"

# Security
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Application
wsgi_app = "app:app"
# If app:app doesn't work, use:
# wsgi_app = "app:create_app()"

# Preload app
preload_app = True

# Max requests per worker
max_requests = 1000
max_requests_jitter = 50