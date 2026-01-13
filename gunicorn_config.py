"""Gunicorn configuration for high-performance API server."""

import multiprocessing

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1  # Formula: (2 x CPU cores) + 1
worker_class = "sync"  # Use sync workers for I/O-bound (SQLite reads)
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "cid_api"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Performance tuning
max_requests = 10000  # Restart worker after this many requests (prevents memory leaks)
max_requests_jitter = 1000  # Add randomness to prevent all workers restarting at once
preload_app = True  # Load application code before forking workers

