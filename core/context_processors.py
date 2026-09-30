"""Cung cấp các quyết định quyền truy cập đã tập trung hóa cho template."""

from core.permissions import can_access_admin, can_manage_accounts
from apps.customers.permissions import has_customer_permission
from apps.seating.permissions import has_seating_permission
from apps.bookings.permissions import has_booking_permission
from apps.menu.permissions import has_menu_permission
from apps.orders.permissions import has_order_permission
from apps.reports.permissions import has_report_permission
from apps.inventory.permissions import has_inventory_permission


def access_policy(request):
    return {
        "access": {
            "can_manage_accounts": can_manage_accounts(request.user),
            "can_access_admin": can_access_admin(request.user),
            "can_view_customers": has_customer_permission(request.user, "view_customer"),
            "can_add_customers": has_customer_permission(request.user, "add_customer"),
            "can_change_customers": has_customer_permission(request.user, "change_customer"),
            "can_delete_customers": has_customer_permission(request.user, "delete_customer"),
            "can_view_customer_logs": has_customer_permission(request.user, "view_customeractivitylog"),
            "can_view_membership_tiers": has_customer_permission(request.user, "view_membershiptier"),
            "can_view_tables": has_seating_permission(request.user, "view_diningtable"),
            "can_view_areas": has_seating_permission(request.user, "view_area"),
            "can_manage_seating": has_seating_permission(request.user, "manage_seating"),
            "can_view_seating_logs": has_seating_permission(request.user, "view_seatingactivitylog"),
            "can_view_bookings": has_booking_permission(request.user, "view_booking"),
            "can_manage_bookings": has_booking_permission(request.user, "manage_booking"),
            "can_view_booking_logs": has_booking_permission(request.user, "view_bookingactivitylog"),
            "can_configure_bookings": has_booking_permission(request.user, "configure_bookings"),
            "can_view_menu": has_menu_permission(request.user, "view_dish"),
            "can_manage_menu": has_menu_permission(request.user, "manage_menu"),
            "can_change_availability": has_menu_permission(request.user, "change_availability"),
            "can_view_menu_logs": has_menu_permission(request.user, "view_menuactivitylog"),
            "can_view_orders": has_order_permission(request.user, "view_order"),
            "can_manage_orders": has_order_permission(request.user, "manage_order"),
            "can_collect_payments": has_order_permission(request.user, "collect_payment"),
            "can_work_kitchen": has_order_permission(request.user, "work_kitchen"),
            "can_cancel_prepared_items": has_order_permission(request.user, "cancel_prepared_item"),
            "can_view_order_logs": has_order_permission(request.user, "view_orderactivitylog"),
            "can_view_invoices": has_order_permission(request.user, "view_invoice"),
            "can_view_reports": has_report_permission(request.user),
            "can_view_inventory": has_inventory_permission(request.user, "view_ingredient"),
            "can_manage_inventory": has_inventory_permission(request.user, "manage_inventory"),
        }
    }
