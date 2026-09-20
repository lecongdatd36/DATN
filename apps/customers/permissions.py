def has_customer_permission(user, permission):
    return bool(
        user and user.is_authenticated and user.is_active
        and user.has_perm(f"customers.{permission}")
    )
