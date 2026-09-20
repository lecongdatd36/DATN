import re

from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Customer, CustomerActivityLog
from .validators import normalize_phone


def customer_list(*, query=""):
    customers = Customer.objects.all()
    query = query.strip()
    if query:
        criteria = Q(full_name__icontains=query) | Q(phone__icontains=query)
        match = re.fullmatch(r"KH([0-9]{1,18})", query, flags=re.IGNORECASE)
        if match:
            criteria |= Q(pk=int(match.group(1)))
        try:
            criteria |= Q(phone=normalize_phone(query))
        except ValidationError:
            pass
        customers = customers.filter(criteria)
    return customers


def customer_logs(*, query="", action=""):
    logs = CustomerActivityLog.objects.select_related("customer")
    if query:
        logs = logs.filter(
            Q(customer_code_snapshot__icontains=query)
            | Q(customer_name_snapshot__icontains=query)
            | Q(performed_by_name_snapshot__icontains=query)
        )
    if action:
        logs = logs.filter(action=action)
    return logs
