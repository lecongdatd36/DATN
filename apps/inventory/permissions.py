def has_inventory_permission(user, permission):
    return bool(user and user.is_authenticated and user.is_active and user.has_perm(f"inventory.{permission}"))
