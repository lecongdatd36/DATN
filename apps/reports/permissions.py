def has_report_permission(user):
    return user.is_authenticated and user.is_active and user.has_perm("reports.view_report")
