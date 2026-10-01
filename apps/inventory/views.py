from django.contrib import messages
from decimal import Decimal
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, F, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import FormView, TemplateView

from core.forms import add_service_errors
from apps.menu.models import Dish
from .forms import (
    IngredientForm, InventoryFilterForm, InventoryTransactionForm, PurchaseReceiptForm,
    PurchaseReceiptLineForm, RecipeIngredientForm, SupplierForm, WasteRecordForm,
)
from .models import (
    Ingredient, InventoryTransaction, PurchaseReceipt, RecipeIngredient, Stocktake, Supplier, WasteRecord,
)
from .permissions import has_inventory_permission
from .services import (
    add_purchase_line, cancel_purchase_receipt, cancel_stocktake, confirm_purchase_receipt,
    create_purchase_receipt, create_stocktake, delete_recipe_line, post_stocktake,
    record_inventory_transaction, record_waste, remove_purchase_line, save_recipe_line,
)


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
        recipe_dishes = list(Dish.objects.select_related("category", "unit").prefetch_related(
            "recipe_ingredients__ingredient"
        ).annotate(
            recipe_line_count=Count("recipe_ingredients")
        ).order_by("category__name", "name", "pk"))
        missing_recipe_count = 0
        unavailable_dish_count = 0
        for dish in recipe_dishes:
            lines = list(dish.recipe_ingredients.all())
            if not lines:
                dish.inventory_portions = 0
                missing_recipe_count += 1
                continue
            dish.inventory_portions = min(int(line.ingredient.stock_quantity // line.quantity) for line in lines)
            if dish.inventory_portions <= 0:
                unavailable_dish_count += 1
        context.update(
            filter_form=filter_form,
            transaction_form=InventoryTransactionForm(),
            ingredients=ingredients,
            recent_transactions=InventoryTransaction.objects.select_related("ingredient", "supplier", "performed_by")[:30],
            suppliers=Supplier.objects.all(),
            recipe_dishes=recipe_dishes,
            ingredient_count=Ingredient.objects.count(),
            low_stock_count=Ingredient.objects.filter(is_active=True, stock_quantity__lte=F("low_stock_threshold")).count(),
            missing_recipe_count=missing_recipe_count,
            unavailable_dish_count=unavailable_dish_count,
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


class InventoryCatalogFormView(InventoryPermissionMixin, FormView):
    permission = "manage_inventory"
    template_name = "staff/inventory/catalog_form.html"
    model = Ingredient
    form_class = IngredientForm
    entity_label = "nguyên liệu"

    def dispatch(self, request, *args, **kwargs):
        self.object = get_object_or_404(self.model, pk=kwargs["pk"]) if "pk" in kwargs else None
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.object
        return kwargs

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            object=self.object,
            entity_label=self.entity_label,
            common_units=getattr(self.form_class, "COMMON_UNITS", ()),
            **kwargs,
        )

    def form_valid(self, form):
        form.save()
        messages.success(self.request, f"Đã lưu {self.entity_label}.")
        return HttpResponseRedirect(reverse("inventory:workspace"))


class IngredientFormView(InventoryCatalogFormView):
    model = Ingredient
    form_class = IngredientForm
    entity_label = "nguyên liệu"


class SupplierFormView(InventoryCatalogFormView):
    model = Supplier
    form_class = SupplierForm
    entity_label = "nhà cung cấp"


class PurchaseReceiptListView(InventoryPermissionMixin, TemplateView):
    template_name = "staff/inventory/purchase_list.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            receipts=PurchaseReceipt.objects.select_related("supplier", "created_by", "confirmed_by").prefetch_related("lines")[:50],
            form=kwargs.get("form") or PurchaseReceiptForm(),
            can_manage=has_inventory_permission(self.request.user, "manage_inventory"),
            **kwargs,
        )

    def post(self, request, *args, **kwargs):
        if not has_inventory_permission(request.user, "manage_inventory"):
            raise PermissionDenied("Bạn không có quyền tạo phiếu nhập.")
        form = PurchaseReceiptForm(request.POST)
        if form.is_valid():
            try:
                receipt = create_purchase_receipt(
                    actor=request.user, supplier_id=form.cleaned_data["supplier"].pk,
                    invoice_number=form.cleaned_data["invoice_number"], note=form.cleaned_data["note"],
                )
            except ValidationError as error:
                add_service_errors(form, error)
            else:
                return redirect("inventory:purchase_detail", pk=receipt.pk)
        return self.render_to_response(self.get_context_data(form=form))


class PurchaseReceiptDetailView(InventoryPermissionMixin, TemplateView):
    template_name = "staff/inventory/purchase_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.receipt = get_object_or_404(
            PurchaseReceipt.objects.select_related("supplier", "created_by", "confirmed_by").prefetch_related("lines__ingredient"),
            pk=kwargs["pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            receipt=self.receipt,
            line_form=kwargs.get("line_form") or PurchaseReceiptLineForm(),
            can_manage=has_inventory_permission(self.request.user, "manage_inventory"),
            **kwargs,
        )

    def post(self, request, *args, **kwargs):
        if not has_inventory_permission(request.user, "manage_inventory"):
            raise PermissionDenied("Bạn không có quyền cập nhật phiếu nhập.")
        action = request.POST.get("action", "add")
        try:
            if action == "confirm":
                confirm_purchase_receipt(actor=request.user, receipt_id=self.receipt.pk)
                messages.success(request, "Đã nhận hàng và cập nhật tồn kho, giá vốn bình quân.")
            elif action == "cancel":
                cancel_purchase_receipt(actor=request.user, receipt_id=self.receipt.pk)
                messages.success(request, "Đã hủy phiếu nhập nháp; tồn kho không thay đổi.")
            elif action == "remove":
                remove_purchase_line(actor=request.user, receipt_id=self.receipt.pk, line_id=int(request.POST["line_id"]))
                messages.success(request, "Đã xóa dòng nguyên liệu.")
            else:
                form = PurchaseReceiptLineForm(request.POST)
                if not form.is_valid():
                    return self.render_to_response(self.get_context_data(line_form=form))
                add_purchase_line(
                    actor=request.user, receipt_id=self.receipt.pk,
                    ingredient_id=form.cleaned_data["ingredient"].pk,
                    quantity=form.cleaned_data["quantity"], unit_cost=form.cleaned_data["unit_cost"],
                )
                messages.success(request, "Đã thêm hoặc cập nhật nguyên liệu trong phiếu.")
        except (ValidationError, ValueError, PurchaseReceipt.DoesNotExist) as error:
            messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "Dữ liệu phiếu nhập không hợp lệ.")
        return redirect("inventory:purchase_detail", pk=self.receipt.pk)


class StocktakeListView(InventoryPermissionMixin, TemplateView):
    template_name = "staff/inventory/stocktake_list.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            stocktakes=Stocktake.objects.select_related("created_by", "posted_by").prefetch_related("lines")[:50],
            can_manage=has_inventory_permission(self.request.user, "manage_inventory"), **kwargs,
        )

    def post(self, request, *args, **kwargs):
        try:
            stocktake = create_stocktake(actor=request.user, note=request.POST.get("note", ""))
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("inventory:stocktake_list")
        return redirect("inventory:stocktake_detail", pk=stocktake.pk)


class StocktakeDetailView(InventoryPermissionMixin, TemplateView):
    template_name = "staff/inventory/stocktake_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.stocktake = get_object_or_404(
            Stocktake.objects.select_related("created_by", "posted_by").prefetch_related("lines__ingredient"), pk=kwargs["pk"]
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            stocktake=self.stocktake, can_manage=has_inventory_permission(self.request.user, "manage_inventory"), **kwargs
        )

    def post(self, request, *args, **kwargs):
        try:
            if request.POST.get("action") == "cancel":
                cancel_stocktake(actor=request.user, stocktake_id=self.stocktake.pk)
                messages.success(request, "Đã hủy phiếu kiểm kê; tồn kho không thay đổi.")
            else:
                quantities = {line.pk: request.POST.get(f"actual_{line.pk}", "") for line in self.stocktake.lines.all()}
                post_stocktake(actor=request.user, stocktake_id=self.stocktake.pk, actual_quantities=quantities)
                messages.success(request, "Đã chốt kiểm kê và ghi nhận toàn bộ chênh lệch.")
        except (ValidationError, ArithmeticError, ValueError) as error:
            messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "Tồn thực tế không hợp lệ.")
        return redirect("inventory:stocktake_detail", pk=self.stocktake.pk)


class WasteRecordView(InventoryPermissionMixin, TemplateView):
    template_name = "staff/inventory/waste.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            form=kwargs.get("form") or WasteRecordForm(),
            records=WasteRecord.objects.select_related("ingredient", "recorded_by")[:50],
            can_manage=has_inventory_permission(self.request.user, "manage_inventory"), **kwargs,
        )

    def post(self, request, *args, **kwargs):
        form = WasteRecordForm(request.POST)
        if form.is_valid():
            try:
                record_waste(
                    actor=request.user, ingredient_id=form.cleaned_data["ingredient"].pk,
                    quantity=form.cleaned_data["quantity"], reason=form.cleaned_data["reason"], note=form.cleaned_data["note"],
                )
            except ValidationError as error:
                add_service_errors(form, error)
            else:
                messages.success(request, "Đã ghi nhận hao hụt và trừ kho.")
                return redirect("inventory:waste")
        return self.render_to_response(self.get_context_data(form=form))


class RecipeView(InventoryPermissionMixin, TemplateView):
    permission = "view_ingredient"
    template_name = "staff/inventory/recipe.html"

    def dispatch(self, request, *args, **kwargs):
        self.dish = get_object_or_404(Dish.objects.select_related("category", "unit"), pk=kwargs["dish_id"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lines = list(
            RecipeIngredient.objects.filter(dish=self.dish)
            .select_related("ingredient")
            .order_by("ingredient__name", "pk")
        )
        estimated_cost = sum((line.estimated_cost for line in lines), Decimal("0"))
        producible_portions = min(
            (int(line.ingredient.stock_quantity // line.quantity) for line in lines),
            default=0,
        )
        context.update(
            dish=self.dish,
            recipe_lines=lines,
            recipe_form=kwargs.get("recipe_form") or RecipeIngredientForm(),
            estimated_cost=estimated_cost,
            estimated_profit=self.dish.price - estimated_cost,
            estimated_margin=(self.dish.price - estimated_cost) / self.dish.price * 100 if self.dish.price else 0,
            producible_portions=producible_portions,
            can_manage=has_inventory_permission(self.request.user, "manage_inventory"),
        )
        return context

    def post(self, request, *args, **kwargs):
        if not has_inventory_permission(request.user, "manage_inventory"):
            raise PermissionDenied("Bạn không có quyền cập nhật công thức món.")
        if request.POST.get("action") == "delete":
            try:
                delete_recipe_line(
                    actor=request.user,
                    dish_id=self.dish.pk,
                    line_id=int(request.POST.get("line_id", "")),
                )
            except (RecipeIngredient.DoesNotExist, TypeError, ValueError):
                messages.error(request, "Dòng công thức không còn tồn tại.")
            else:
                messages.success(request, "Đã xóa nguyên liệu khỏi công thức.")
            return redirect("inventory:recipe", dish_id=self.dish.pk)

        form = RecipeIngredientForm(request.POST)
        if form.is_valid():
            try:
                save_recipe_line(
                    actor=request.user,
                    dish_id=self.dish.pk,
                    ingredient_id=form.cleaned_data["ingredient"].pk,
                    quantity=form.cleaned_data["quantity"],
                )
            except ValidationError as error:
                add_service_errors(form, error)
            else:
                messages.success(request, "Đã cập nhật định lượng nguyên liệu.")
                return redirect("inventory:recipe", dish_id=self.dish.pk)
        return self.render_to_response(self.get_context_data(recipe_form=form))
