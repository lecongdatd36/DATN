from core.db_locks import transaction_lock


def lock_menu():
    """Inside atomic, before actor/row locks; after seating lock if both are used."""
    transaction_lock(81723003)
