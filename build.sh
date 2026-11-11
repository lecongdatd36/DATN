#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
if [ "${ENABLE_FACE_ATTENDANCE:-0}" = "1" ]; then
    pip install -r requirements-attendance.txt
    python scripts/setup_attendance_models.py --root "${ATTENDANCE_MODEL_ROOT:-artifacts/attendance/models}"
fi
python scripts/compile_translations.py
python manage.py collectstatic --no-input
python manage.py migrate
# Chat history and rate limits use a shared database cache. This is idempotent.
python manage.py createcachetable qlnh_chatbot_cache
