from django.db import connection


def lock_menu():
    """Inside atomic, before actor/row locks; after seating lock if both are used."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [81723003])
