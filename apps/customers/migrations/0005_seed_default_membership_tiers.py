from django.db import migrations


def seed_default_tiers(apps, schema_editor):
    alias = schema_editor.connection.alias
    MembershipTier = apps.get_model("customers", "MembershipTier")
    Customer = apps.get_model("customers", "Customer")
    if MembershipTier.objects.using(alias).exists():
        return
    tiers = [
        MembershipTier.objects.using(alias).create(name="Đồng", minimum_spending=0, discount_percent=0),
        MembershipTier.objects.using(alias).create(name="Bạc", minimum_spending=2_000_000, discount_percent=3),
        MembershipTier.objects.using(alias).create(name="Vàng", minimum_spending=5_000_000, discount_percent=5),
        MembershipTier.objects.using(alias).create(name="Kim cương", minimum_spending=10_000_000, discount_percent=10),
    ]
    for customer in Customer.objects.using(alias).all():
        tier = next(item for item in reversed(tiers) if item.minimum_spending <= customer.total_spending)
        customer.membership_tier_id = tier.pk
        customer.save(update_fields=("membership_tier",))


class Migration(migrations.Migration):
    dependencies = [("customers", "0004_seed_membership_permissions")]
    operations = [migrations.RunPython(seed_default_tiers, migrations.RunPython.noop)]
