import os


bind = os.getenv("GUNICORN_BIND", "127.0.0.1:4000")
workers = int(os.getenv("GUNICORN_WORKERS", "3"))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
accesslog = "-"
errorlog = "-"
capture_output = True
