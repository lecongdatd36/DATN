from core.permissions import can_manage_accounts


def can_manage_employees(user):
    return can_manage_accounts(user)
