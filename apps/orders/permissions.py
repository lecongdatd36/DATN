def has_order_permission(user, permission):
    return user.is_authenticated and user.is_active and user.has_perm(f"orders.{permission}")
