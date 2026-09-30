from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from django.utils import timezone

from .models import Customer, CustomerActivityLog, MembershipTier
from .permissions import has_customer_permission
from .validators import normalize_phone


def tier_for_spending(total_spending):
    return MembershipTier.objects.filter(
        is_active=True, minimum_spending__lte=total_spending
    ).order_by("-minimum_spending", "-pk").first()


@transaction.atomic
def recalculate_membership_tiers():
    """Refresh the cached tier on every customer after tier rules change."""
    tiers = list(MembershipTier.objects.filter(is_active=True).order_by("-minimum_spending", "-pk"))
    changed = []
    now = timezone.now()
    for customer in Customer.objects.select_for_update().all():
        tier = next((item for item in tiers if item.minimum_spending <= customer.total_spending), None)
        tier_id = tier.pk if tier else None
        if customer.membership_tier_id != tier_id:
            customer.membership_tier_id = tier_id
            customer.updated_at = now
            changed.append(customer)
    if changed:
        Customer.objects.bulk_update(changed, ("membership_tier", "updated_at"))
    return len(changed)


def _lock_actor(actor, permission):
    if not actor.is_authenticated or not actor.pk:
        raise PermissionDenied("Bạn không có quyền thao tác khách hàng.")
    actor = get_user_model().objects.select_for_update().filter(pk=actor.pk).first()
    if actor is None or not has_customer_permission(actor, permission):
        raise PermissionDenied("Bạn không có quyền thao tác khách hàng.")
    return actor


def _set_data(customer, full_name, phone):
    customer.full_name = " ".join(full_name.split()) if isinstance(full_name, str) else ""
    try:
        customer.phone = normalize_phone(phone)
    except ValidationError as error:
        raise ValidationError({"phone": error.messages}) from error
    customer.full_clean()


def _save(customer):
    try:
        # Savepoint keeps the outer transaction usable after a concurrent duplicate.
        with transaction.atomic():
            customer.save()
    except IntegrityError as error:
        if Customer.objects.filter(phone=customer.phone).exclude(pk=customer.pk).exists():
            raise ValidationError({"phone": "Số điện thoại đã có hồ sơ khách hàng."}) from error
        raise


def _log(actor, customer, action, description):
    CustomerActivityLog.objects.create(
        customer=customer,
        customer_code_snapshot=customer.customer_code,
        customer_name_snapshot=customer.full_name,
        performed_by=actor,
        performed_by_name_snapshot=actor.username,
        action=action,
        description=description,
    )


@transaction.atomic
def create_customer(*, actor, full_name, phone):
    actor = _lock_actor(actor, "add_customer")
    base_tier = tier_for_spending(0)
    customer = Customer(membership_tier=base_tier)
    _set_data(customer, full_name, phone)
    _save(customer)
    _log(actor, customer, CustomerActivityLog.Action.CREATE, "Thêm hồ sơ khách hàng.")
    return customer


@transaction.atomic
def update_customer(*, actor, customer_id, full_name, phone):
    actor = _lock_actor(actor, "change_customer")
    customer = Customer.objects.select_for_update().get(pk=customer_id)
    before = (customer.full_name, customer.phone)
    _set_data(customer, full_name, phone)
    changed = [label for label, old, new in zip(
        ("họ tên", "số điện thoại"), before, (customer.full_name, customer.phone),
    ) if old != new]
    if changed:
        _save(customer)
        _log(actor, customer, CustomerActivityLog.Action.UPDATE, "Cập nhật " + ", ".join(changed) + ".")
    return customer


@transaction.atomic
def delete_customer(*, actor, customer_id):
    actor = _lock_actor(actor, "delete_customer")
    customer = Customer.objects.select_for_update().get(pk=customer_id)
    _log(actor, customer, CustomerActivityLog.Action.DELETE, "Xóa hồ sơ khách hàng.")
    try:
        customer.delete()
    except (ProtectedError, RestrictedError) as error:
        raise ValidationError("Khách hàng đã có dữ liệu nghiệp vụ liên kết nên không thể xóa.") from error
