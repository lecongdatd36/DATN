#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
# Chat history and rate limits use a shared database cache. This is idempotent.
python manage.py createcachetable qlnh_chatbot_cache
