#!/bin/sh
set -e

# P11: create the MinIO bucket idempotently before the app serves. No manual `mc`.
python manage.py ensure_bucket

# Compose passes migrate + collectstatic + gunicorn as the command ("$@").
exec "$@"
