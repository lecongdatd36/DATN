#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-QLNH.sqlserver_settings}"
exec python -m gunicorn QLNH.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --threads "${GUNICORN_THREADS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --error-logfile -
