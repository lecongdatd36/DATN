from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.shortcuts import redirect
from django.views.generic import TemplateView

from core.forms import add_service_errors
from .forms import InventoryFilterForm, InventoryTransactionForm
from .models import Ingredient, InventoryTransaction, Supplier
from .permissions import has_inventory_permission
from .services import record_inventory_transaction


class InventoryPermissionMixin(AccessMixin):
    permission = "view_ingredient"

    def dispatch(self, request, *args, **kwargs):
        if not has_inventory_permission(request.user, self.permission):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class InventoryWorkspaceView(InventoryPermissionMixin, TemplateView):
    template_name = "staff/inventory/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_form = InventoryFilterForm(self.request.GET)
        ingredients = Ingredient.objects.all()
        if filter_form.is_valid():
            q = filter_form.cleaned_data["q"]
            if q:
                ingredients = ingredients.filter(Q(code__icontains=q) | Q(name__icontains=q))
            if filter_form.cleaned_data["low_stock"]:
                ingredients = ingredients.filter(stock_quantity__lte=F("low_stock_threshold"))
        context.update(
            filter_form=filter_form,
            transaction_form=InventoryTransactionForm(),
            ingredients=ingredients,
            recent_transactions=InventoryTransaction.objects.select_related("ingredient", "supplier", "performed_by")[:30],
            suppliers=Supplier.objects.filter(is_active=True),
            can_manage=has_inventory_permission(self.request.user, "manage_inventory"),
        )
        return context

    def post(self, request, *args, **kwargs):
        if not has_inventory_permission(request.user, "manage_inventory"):
            return self.handle_no_permission()
        form = InventoryTransactionForm(request.POST)
        if form.is_valid():
            try:
                record_inventory_transaction(
                    actor=request.user,
                    ingredient_id=form.cleaned_data["ingredient"].pk,
                    transaction_type=form.cleaned_data["transaction_type"],
                    quantity=form.cleaned_data["quantity"],
                    unit_cost=form.cleaned_data["unit_cost"] or 0,
                    supplier_id=form.cleaned_data["supplier"].pk if form.cleaned_data["supplier"] else None,
                    note=form.cleaned_data["note"],
                )
            except ValidationError as error:
                add_service_errors(form, error)
            else:
                messages.success(request, "Đã ghi nhận giao dịch kho.")
                return redirect("inventory:workspace")
        context = self.get_context_data()
        context["transaction_form"] = form
        return self.render_to_response(context)
