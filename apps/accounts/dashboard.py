"""Read-only, permission-scoped operational overview; Vietnam calendar boundaries."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from django.db.models import Count, Sum, F, Q, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncDate
from django.utils import timezone
from apps.orders.models import Order, Invoice, OrderItem, OrderActivityLog
from apps.bookings.models import Booking
from apps.seating.models import DiningTable
from apps.inventory.models import Ingredient, InventoryTransaction


def dashboard_data(user, days=7):
    now = timezone.now()
    today = timezone.localdate(now)
    start = timezone.make_aware(datetime.combine(today, time.min))
    end = start + timedelta(days=1)
    since = start-timedelta(days=days-1)
    month = start-timedelta(days=29)
    result = {"days": days, "today": today, "now": now}
    invoices = Invoice.objects.filter(status=Invoice.Status.PAID)
    result['revenue'] = invoices.filter(closed_at__gte=start, closed_at__lt=end).aggregate(total=Sum('total'))['total'] or 0
    revenue_rows = {row['day']:row['total'] for row in invoices.filter(closed_at__gte=since, closed_at__lt=end)
        .annotate(day=TruncDate('closed_at')).values('day').annotate(total=Sum('total'))}
    can_orders = user.has_perm('orders.view_order')
    orders = Order.objects.filter(created_at__gte=start, created_at__lt=end)
    result['order_count'] = orders.count() if can_orders else None
    order_rows = {row['day']:row['total'] for row in Order.objects.filter(created_at__gte=since, created_at__lt=end)
        .annotate(day=TruncDate('created_at')).values('day').annotate(total=Count('pk'))} if can_orders else {}
    result['chart'] = {'labels':[], 'revenue':[], 'orders':[], 'show_orders':can_orders}
    for offset in range(days):
        day = today-timedelta(days=days-1-offset)
        result['chart']['labels'].append(day.strftime('%d/%m'))
        result['chart']['revenue'].append(int(revenue_rows.get(day, 0)))
        result['chart']['orders'].append(order_rows.get(day, 0))
    result['distribution'] = [{'label':str(label),'count':orders.filter(status=status).count()} for status,label in Order.Status.choices] if can_orders else []
    result['recent_orders'] = orders.select_related('customer','table','booking__table').order_by('-created_at','-pk')[:5] if can_orders else []
    if user.has_perm('seating.view_diningtable'):
        tables = DiningTable.objects.filter(is_active=True, area__is_active=True)
        result['table_count'] = tables.count()
        result['occupied_count'] = tables.filter(status='OCCUPIED').count()
    if user.has_perm('bookings.view_booking'):
        bookings = Booking.objects.filter(starts_at__gte=start, starts_at__lt=end, is_walk_in=False).exclude(status__in=['CANCELLED','NO_SHOW'])
        result['booking_count'] = bookings.count()
        result['upcoming_bookings'] = Booking.objects.filter(starts_at__gte=now, status__in=['PENDING','CONFIRMED'], is_walk_in=False).select_related('customer','table').order_by('starts_at','pk')[:4]
    result['top_dishes'] = OrderItem.objects.filter(order__invoice__status='PAID',order__invoice__closed_at__gte=month,order__invoice__closed_at__lt=end).exclude(status='CANCELLED').values('dish_name','unit_name').annotate(quantity=Sum('quantity')).order_by('-quantity','dish_name')[:5]
    if user.has_perm('inventory.view_ingredient'):
        result['low_stock'] = Ingredient.objects.filter(is_active=True,stock_quantity__lte=F('low_stock_threshold')).order_by('stock_quantity','name')[:5]
        amount=ExpressionWrapper(F('quantity')*F('unit_cost'),output_field=DecimalField(max_digits=22,decimal_places=3))
        result['top_ingredients'] = InventoryTransaction.objects.filter(created_at__gte=month,created_at__lt=end,
            transaction_type__in=['SALE_USAGE','SALE_RETURN']).values('ingredient__name','ingredient__unit').annotate(
            used=Sum('quantity',filter=Q(transaction_type='SALE_USAGE'),default=Decimal(0))-Sum('quantity',filter=Q(transaction_type='SALE_RETURN'),default=Decimal(0)),
            value=Sum(amount,filter=Q(transaction_type='SALE_USAGE'),default=Decimal(0))-Sum(amount,filter=Q(transaction_type='SALE_RETURN'),default=Decimal(0))
        ).filter(used__gt=0).order_by('-value','ingredient__name')[:5]
    result['recent_logs'] = OrderActivityLog.objects.select_related('order').order_by('-created_at','-pk')[:5] if user.has_perm('orders.view_orderactivitylog') else []
    return result
