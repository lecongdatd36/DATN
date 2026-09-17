from django.db.models import Q

from apps.accounts.models import User


def account_list(*, query="", status=""):
    accounts = User.objects.all()
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
    return accounts.order_by("username", "pk")
