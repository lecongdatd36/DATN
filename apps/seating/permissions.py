def has_seating_permission(user, permission):
    return user.is_authenticated and user.is_active and user.has_perm(f"seating.{permission}")
