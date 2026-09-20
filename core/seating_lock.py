from django.db import connection


def lock_seating_schedule():
    """Call inside atomic before actor/table locks in catalog and booking writes."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [81723002])
