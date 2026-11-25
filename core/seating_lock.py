from core.db_locks import transaction_lock


def lock_seating_schedule():
    """Call inside atomic before actor/table locks in catalog and booking writes."""
    transaction_lock(81723002)
