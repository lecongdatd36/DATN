from uuid import uuid4
from django import forms
from django.utils import timezone
from apps.accounts.forms import BootstrapFormMixin
from apps.bookings.forms import PublicReservationForm
from apps.menu.models import Dish
from apps.customers.validators import normalize_phone
from .models import Reservation, ReservationPolicy


class ItemsMixin:
    def add_items(self, initial_items=None):
        initial_items=initial_items or {}
        self.dishes=list(Dish.objects.select_related("category","unit").filter(category__is_active=True,unit__is_active=True).exclude(status="INACTIVE").order_by("category__name","name"))
        for dish in self.dishes:
            self.fields[f"qty_{dish.pk}"]=forms.IntegerField(label=f"{dish.name} · {dish.price:,.0f}đ",min_value=0,max_value=100,required=False,
                initial=initial_items.get(dish.pk,0),widget=forms.NumberInput(attrs={"class":"form-control","min":0,"max":100,"inputmode":"numeric"}))
            self.fields[f"note_{dish.pk}"]=forms.CharField(label="Ghi chú món",required=False,max_length=500,widget=forms.TextInput(attrs={"class":"form-control","placeholder":"Ít cay, không hành…"}))
        policy,_=ReservationPolicy.objects.get_or_create(pk=1)
        allowed=set(policy.allowed_dishes.values_list("pk",flat=True))
        self.item_rows=[{"dish":dish,"quantity":self[f"qty_{dish.pk}"],"note":self[f"note_{dish.pk}"],"advance_allowed":dish.pk in allowed} for dish in self.dishes]

    def selected_items(self):
        return [{"dish_id":dish.pk,"quantity":self.cleaned_data.get(f"qty_{dish.pk}"),"note":self.cleaned_data.get(f"note_{dish.pk}","")} for dish in self.dishes if self.cleaned_data.get(f"qty_{dish.pk}")]


class ReservationDetailsForm(PublicReservationForm):
    mode=forms.ChoiceField(label="Cách chuẩn bị món",choices=Reservation.Mode.choices)
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
        known={row["quantity"].name for row in self.item_rows}
        if any(key.startswith("qty_") and key not in known and value not in ("", "0") for key,value in self.data.items()):
            raise forms.ValidationError("Một món đã ngừng phục vụ. Vui lòng kiểm tra giỏ và chọn lại món.")
        selected=[row for row in self.item_rows if data.get(row["quantity"].name)]
        if self.mode=="READY" and not selected:
            raise forms.ValidationError("Vui lòng chọn ít nhất một món để nhà hàng chuẩn bị theo giờ hẹn.")
        if self.require_items and not selected:
            raise forms.ValidationError("Vui lòng chọn ít nhất một món để đặt món trước.")
        if len(selected)>50:
            raise forms.ValidationError("Mỗi lượt đặt được chọn tối đa 50 món khác nhau.")
        for row in selected:
            if row["dish"].status!="AVAILABLE":
                self.add_error(row["quantity"].name,"Món hiện đã hết. Vui lòng bỏ khỏi giỏ.")
            elif self.mode=="READY" and not row["advance_allowed"]:
                self.add_error(row["quantity"].name,"Món này chỉ chế biến khi khách đến. Vui lòng bỏ khỏi giỏ hoặc đổi cách chuẩn bị.")
        return data


class PreorderChoiceForm(forms.Form):
    decision=forms.ChoiceField(choices=(("yes","Có, tôi muốn đặt món trước"),("no","Không, chỉ đặt bàn")))
    mode=forms.ChoiceField(label="Nếu đặt món trước, bạn muốn nhà hàng chuẩn bị thế nào?",
        choices=Reservation.Mode.choices,initial="TABLE",required=False)

    def clean(self):
        data=super().clean()
        data["mode"]=data.get("mode") or "TABLE"
        if data.get("decision")=="no":
            data["mode"]="TABLE"
        return data


class OnlineForm(ItemsMixin, ReservationDetailsForm):
    agree=forms.BooleanField(label="Tôi đã đọc tiền cọc, thời hạn thanh toán và điều kiện đổi/hủy.")

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.add_items()


class OfferForm(ItemsMixin, BootstrapFormMixin, forms.Form):
    revision=forms.IntegerField(widget=forms.HiddenInput)
    starts_at=forms.DateTimeField(label="Giờ hẹn khách",widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"}))
    prep_starts_at=forms.DateTimeField(label="Bắt đầu chuẩn bị",widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"}))
    ready_by=forms.DateTimeField(label="Sẵn sàng phục vụ",widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"}))
    note=forms.CharField(label="Nội dung nhà hàng chốt với khách",max_length=1000,widget=forms.Textarea(attrs={"rows":3}))

    def __init__(self,*args,reservation,**kwargs):
        super().__init__(*args,**kwargs)
        items=list(reservation.items.all())
        self.add_items({item.dish_id:item.quantity for item in items})
        for item in items:
            self.initial[f"note_{item.dish_id}"]=item.note
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
                self.add_error(name,"Chọn từ 1 đến 1440 phút.")
        if data.get("free_cancel_hours",0)>168:
            self.add_error("free_cancel_hours","Tối đa 168 giờ.")
        return data


class LookupForm(BootstrapFormMixin,forms.Form):
    reservation_code=forms.RegexField(r"^(?:OL|DB)[0-9]{1,18}$",label="Mã đặt bàn",max_length=20)
    phone=forms.CharField(label="Số điện thoại khi đặt",max_length=20)

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])
