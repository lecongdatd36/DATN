from django.utils.translation import gettext_lazy as _
from uuid import uuid4
from django import forms
from django.utils import timezone
from apps.accounts.forms import BootstrapFormMixin
from apps.bookings.forms import PublicReservationForm
from apps.menu.models import Dish
from apps.menu.combos import combo_catalog, expand_selections
from apps.customer_portal.localization import public_name
from apps.customers.validators import normalize_phone
from .models import Reservation, ReservationPolicy


class ItemsMixin:
    def add_items(self, initial_items=None, initial_combos=None):
        initial_items=initial_items or {}
        self.dishes=list(Dish.objects.select_related("category","unit").filter(category__is_active=True,unit__is_active=True).exclude(status="INACTIVE").order_by("category__name","name"))
        for dish in self.dishes:
            self.fields[f"qty_{dish.pk}"]=forms.IntegerField(label=f"{public_name(dish)} · {dish.price:,.0f}₫",min_value=0,max_value=100,required=False,
                initial=initial_items.get(dish.pk,0),widget=forms.NumberInput(attrs={"class":"form-control","min":0,"max":100,"inputmode":"numeric"}))
            self.fields[f"note_{dish.pk}"]=forms.CharField(label=_("Ghi chú món"),required=False,max_length=500,widget=forms.TextInput(attrs={"class":"form-control","placeholder":_("Ít cay, không hành…")}))
        policy,policy_created=ReservationPolicy.objects.get_or_create(pk=1)
        allowed=set(policy.allowed_dishes.values_list("pk",flat=True))
        self.item_rows=[{"dish":dish,"quantity":self[f"qty_{dish.pk}"],"note":self[f"note_{dish.pk}"],"advance_allowed":dish.pk in allowed} for dish in self.dishes]
        initial_combos=initial_combos or {}
        self.combos=list(combo_catalog(active_only=False))
        self.combo_rows=[]
        for combo in self.combos:
            if not combo.is_active and combo.pk not in initial_combos and str(self.data.get(f"cqty_{combo.pk}",0)) in ("0",""):
                continue
            maximum=min((100//part.quantity for part in combo.components),default=1)
            self.fields[f"cqty_{combo.pk}"]=forms.IntegerField(label=public_name(combo),min_value=0,max_value=maximum,required=False,
                initial=initial_combos.get(combo.pk,0),widget=forms.NumberInput(attrs={"class":"form-control","min":0,"max":maximum,"inputmode":"numeric"}))
            self.fields[f"cnote_{combo.pk}"]=forms.CharField(label=_("Ghi chú combo"),required=False,max_length=300,
                widget=forms.TextInput(attrs={"class":"form-control","placeholder":_("Ghi chú cho cả combo…")}))
            self.combo_rows.append({"combo":combo,"quantity":self[f"cqty_{combo.pk}"],"note":self[f"cnote_{combo.pk}"],
                "advance_allowed":all(part.dish_id in allowed for part in combo.components)})

    def selected_items(self):
        dishes=[{"dish_id":dish.pk,"quantity":self.cleaned_data.get(f"qty_{dish.pk}"),"note":self.cleaned_data.get(f"note_{dish.pk}","")} for dish in self.dishes if self.cleaned_data.get(f"qty_{dish.pk}")]
        return dishes+[{"combo_id":row["combo"].pk,"quantity":self.cleaned_data.get(row["quantity"].name),
            "note":self.cleaned_data.get(row["note"].name,"")} for row in self.combo_rows if self.cleaned_data.get(row["quantity"].name)]


class ReservationDetailsForm(PublicReservationForm):
    mode=forms.ChoiceField(label=_("Cách chuẩn bị món"),choices=[(value,_(label)) for value,label in Reservation.Mode.choices])
    request_key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid4)

    def __init__(self,*args,booking_flow=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.booking_flow=booking_flow
        if booking_flow=="table":
            self.fields.pop("mode")

    def clean(self):
        data=super().clean()
        if self.booking_flow=="table":
            data["mode"]="TABLE"
        return data


class PreorderCartForm(ItemsMixin, forms.Form):
    def __init__(self,*args,mode="TABLE",require_items=True,**kwargs):
        super().__init__(*args,**kwargs)
        self.mode=mode
        self.require_items=require_items
        self.add_items()

    def clean(self):
        data=super().clean()
        known={row["quantity"].name for row in self.item_rows+self.combo_rows}
        if any(key.startswith(("qty_","cqty_")) and key not in known and value not in (None,"", "0",0) for key,value in self.data.items()):
            raise forms.ValidationError(_("Một món đã ngừng phục vụ. Vui lòng kiểm tra giỏ và chọn lại món."))
        selected=[row for row in self.item_rows if data.get(row["quantity"].name)]
        selected_combos=[row for row in self.combo_rows if data.get(row["quantity"].name)]
        if self.mode=="READY" and not (selected or selected_combos):
            raise forms.ValidationError(_("Vui lòng chọn ít nhất một món để nhà hàng chuẩn bị theo giờ hẹn."))
        if self.require_items and not (selected or selected_combos):
            raise forms.ValidationError(_("Vui lòng chọn ít nhất một món để đặt món trước."))
        if len(selected)+len(selected_combos)>50:
            raise forms.ValidationError(_("Mỗi lượt đặt được chọn tối đa 50 món khác nhau."))
        for row in selected:
            if row["dish"].status!="AVAILABLE":
                self.add_error(row["quantity"].name,_("Món hiện đã hết. Vui lòng bỏ khỏi giỏ."))
            elif self.mode=="READY" and not row["advance_allowed"]:
                self.add_error(row["quantity"].name,_("Món này chỉ chế biến khi khách đến. Vui lòng bỏ khỏi giỏ hoặc đổi cách chuẩn bị."))
        for row in selected_combos:
            if not row["combo"].is_orderable:
                self.add_error(row["quantity"].name,_("Combo có món hết/ngừng bán. Vui lòng chọn lại."))
            elif self.mode=="READY" and not row["advance_allowed"]:
                self.add_error(row["quantity"].name,_("Có thành phần combo chưa cho phép chuẩn bị theo giờ."))
        if not self.errors:
            expand_selections(self.selected_items())
        return data


class PreorderChoiceForm(forms.Form):
    decision=forms.ChoiceField(choices=(("yes","Có, tôi muốn đặt món trước"),("no","Không, chỉ đặt bàn")))
    mode=forms.ChoiceField(label=_("Nếu đặt món trước, bạn muốn nhà hàng chuẩn bị thế nào?"),
        choices=[(value,_(label)) for value,label in Reservation.Mode.choices],initial="TABLE",required=False)

    def clean(self):
        data=super().clean()
        data["mode"]=data.get("mode") or "TABLE"
        if data.get("decision")=="no":
            data["mode"]="TABLE"
        return data


class OnlineForm(ItemsMixin, ReservationDetailsForm):
    agree=forms.BooleanField(label=_("Tôi đã đọc tiền cọc, thời hạn thanh toán và điều kiện đổi/hủy."))

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.add_items()


class OfferForm(ItemsMixin, BootstrapFormMixin, forms.Form):
    revision=forms.IntegerField(widget=forms.HiddenInput)
    starts_at=forms.DateTimeField(label=_("Giờ hẹn khách"),widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"}))
    prep_starts_at=forms.DateTimeField(label=_("Bắt đầu chuẩn bị"),widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"}))
    ready_by=forms.DateTimeField(label=_("Sẵn sàng phục vụ"),widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"}))
    note=forms.CharField(label=_("Nội dung nhà hàng chốt với khách"),max_length=1000,widget=forms.Textarea(attrs={"rows":3}))

    def __init__(self,*args,reservation,**kwargs):
        super().__init__(*args,**kwargs)
        items=list(reservation.items.all())
        self.add_items({item.dish_id:item.quantity for item in items if not item.combo_id},
            {item["id"]:item["quantity"] for item in reservation.combo_snapshot})
        for item in items:
            if not item.combo_id:
                self.initial[f"note_{item.dish_id}"]=item.note
        for item in reservation.combo_snapshot:
            self.initial[f"cnote_{item['id']}"]=item.get("note","")
        if reservation.mode=="TABLE":
            for key in ("prep_starts_at","ready_by"):
                self.fields[key].required=False
                self.fields[key].widget=forms.HiddenInput()


class PolicyForm(BootstrapFormMixin,forms.ModelForm):
    class Meta:
        model=ReservationPolicy
        fields=("table_deposit","ready_percent","hold_minutes","offer_minutes","minimum_lead_minutes","free_cancel_hours","allowed_dishes")

    def clean(self):
        data=super().clean()
        for name in ("hold_minutes","offer_minutes","minimum_lead_minutes"):
            if data.get(name) is not None and not 1<=data[name]<=1440:
                self.add_error(name,_("Chọn từ 1 đến 1440 phút."))
        if data.get("free_cancel_hours",0)>168:
            self.add_error("free_cancel_hours",_("Tối đa 168 giờ."))
        return data


class LookupForm(BootstrapFormMixin,forms.Form):
    reservation_code=forms.RegexField(r"^(?:OL|DB)[0-9]{1,18}$",label=_("Mã đặt bàn"),max_length=20)
    phone=forms.CharField(label=_("Số điện thoại khi đặt"),max_length=20)

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])
