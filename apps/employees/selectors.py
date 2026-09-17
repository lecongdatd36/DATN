from django.db.models import Q

from .models import EmployeeProfile


def employee_list(*, query="", position="", status=""):
    employees = EmployeeProfile.objects.select_related("user")
    if query:
        employees = employees.filter(
            Q(employee_code__icontains=query)
            | Q(full_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(user__username__icontains=query)
        )
    if position:
        employees = employees.filter(job_position=position)
    if status:
        employees = employees.filter(employment_status=status)
    return employees.order_by("employee_code", "pk")
