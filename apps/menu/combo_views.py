from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import FormView, ListView

from .combos import combo_catalog, save_combo
from .forms import RevisionForm
from .models import Combo, Dish
from .views import MenuPermissionMixin
from core.forms import add_service_errors


class ComboForm(RevisionForm):
    class Meta:
        model = Combo
        fields = ("code", "name", "name_en", "description", "description_en", "people", "price", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 3}),
            "people": forms.NumberInput(attrs={"min": 1, "max": 20}),
            "price": forms.NumberInput(attrs={"min": 1, "step": 1})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        initial = {part.dish_id: part.quantity for part in self.instance.items.all()} if self.instance.pk else {}
        self.component_rows = []
        for dish in Dish.objects.select_related("category", "unit").filter(~Q(status="INACTIVE")|Q(pk__in=initial)):
            key = f"qty_{dish.pk}"
            self.fields[key] = forms.IntegerField(label=dish.name, min_value=0, max_value=10, required=False,
                initial=initial.get(dish.pk, 0), widget=forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 10}))
            self.component_rows.append({"dish": dish, "quantity": self[key]})

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        import re
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,19}", code):
            raise forms.ValidationError("Mã gồm A–Z, số, gạch dưới hoặc gạch ngang, tối đa 20 ký tự.")
        return code

    def selected_items(self):
        return [{"dish_id": row["dish"].pk, "quantity": self.cleaned_data[row["quantity"].name]}
            for row in self.component_rows if self.cleaned_data.get(row["quantity"].name)]


class ComboListView(MenuPermissionMixin, ListView):
    template_name = "menu/combos.html"
    context_object_name = "combos"

    def get_queryset(self):
        return combo_catalog(active_only=False)


class ComboFormView(MenuPermissionMixin, FormView):
    template_name = "menu/combo_form.html"
    form_class = ComboForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.object = get_object_or_404(Combo, pk=self.kwargs["pk"]) if "pk" in self.kwargs else None
        kwargs["instance"] = self.object
        return kwargs

    def form_valid(self, form):
        data = {key: form.cleaned_data[key] for key in ("code", "name", "name_en", "description", "description_en", "people", "price", "is_active", "expected_revision")}
        try:
            save_combo(actor=self.request.user, combo_id=self.object.pk if self.object else None,
                items=form.selected_items(), **data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        messages.success(self.request, "Đã lưu combo. Lịch đặt cũ giữ nguyên món và giá đã ghi nhận.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("menu:combo_list")
