from django.db.models import Q

from apps.accounts.models import User
from apps.employees.models import EmployeeProfile


def account_list(*, query="", status="", account_type="", position=None):
    accounts = User.objects.select_related("employee_profile", "employee_profile__job_position")
    query = query.strip()
    if query:
        accounts = accounts.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    if status == "active":
        accounts = accounts.filter(is_active=True)
    elif status == "inactive":
        accounts = accounts.filter(is_active=False)
    if position:
        accounts = accounts.filter(employee_profile__job_position=position)
    if account_type == "MANAGER":
        accounts = accounts.filter(employee_profile__job_position__code="MANAGER")
    elif account_type == "EMPLOYEE":
        accounts = accounts.exclude(employee_profile__job_position__code="MANAGER")
    return accounts.order_by("username", "pk")
