def has_booking_permission(user, permission):
    return user.is_authenticated and user.is_active and user.has_perm(f"bookings.{permission}")
