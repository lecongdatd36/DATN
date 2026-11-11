from django.utils.translation import gettext as _
from datetime import timedelta
from functools import wraps
from uuid import UUID
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError,ImproperlyConfigured
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404,render,redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare,salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET,require_POST
from apps.bookings.permissions import has_booking_permission
from apps.orders.permissions import has_order_permission
from apps.orders.zalopay import MIN_EXPIRE_SECONDS, enabled as zalopay_enabled
from core.permissions import can_manage_accounts
from . import services
from .forms import OnlineForm,ReservationDetailsForm,PreorderChoiceForm,PreorderCartForm,OfferForm,PolicyForm,LookupForm
from .models import Reservation,PreorderItem,DepositPayment,ReservationPolicy


def private_response(response):
    # Keep the origin for same-site CSRF form posts, hide capability URLs from
    # external destinations (including the payment provider).
    response["Referrer-Policy"]="same-origin"
    response["X-Robots-Tag"]="noindex, nofollow"
    return response


def remember_private_reservation(request,row):
    # A valid capability visit grants this browser access to its own recent
    # reservations. Code + phone alone must never grant that access.
    tokens=request.session.get("private_reservations",[])
    token=str(row.access_token)
    request.session["private_reservations"]=[value for value in tokens if value!=token][-19:]+[token]


def owns_reservation(request,row):
    if str(row.access_token) in request.session.get("private_reservations",[]):
        return True
    if not request.session.session_key:
        return False
    digest=salted_hmac("reservation.source",request.session.session_key,algorithm="sha256").hexdigest()
    return constant_time_compare(row.source_digest,digest)


def error_message(request,error):
    messages.error(request," ".join(error.messages) if isinstance(error,ValidationError) else str(error))


def staff(view):
    @login_required
    @never_cache
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not has_booking_permission(request.user,"manage_booking"):
            raise PermissionDenied
        return view(request,*args,**kwargs)
    return wrapped


@never_cache
def create(request):
    if not request.session.session_key:
        request.session.create()
    # Continue accepting the previous form's POST for existing open tabs.
    if request.method=="POST" and "step" not in request.POST:
        return submit_legacy(request,services.policy_snapshot())
    draft=request.session.get("reservation_draft",{})
    form=ReservationDetailsForm(request.POST if request.method=="POST" else None,
        initial=draft.get("details",{}),booking_flow="table")
    if request.method=="GET":
        # Homepage shortcuts only prefill the form. Holding a table still needs
        # the existing POST, full validation, consent and transaction workflow.
        day=request.GET.get("booking_date","")
        clock=request.GET.get("booking_time","")
        hints={"starts_at":f"{day}T{clock}" if day and clock else "",
            "party_size":request.GET.get("party_size","")}
        for name,value in hints.items():
            if value:
                try:
                    form.initial[name]=form.fields[name].clean(value)
                except ValidationError:
                    pass
    if request.method=="POST" and form.is_valid():
        details={key:request.POST.get(key,"") for key in form.fields}
        details["mode"]=draft.get("details",{}).get("mode","TABLE")
        from_storefront=bool(draft.get("from_storefront") and any(str(value or "0")!="0" for key,value in draft.get("cart",{}).items() if key.startswith(("qty_","cqty_"))))
        request.session["reservation_draft"]={"flow":"preorder" if from_storefront else "undecided","details":details,
            "cart":draft.get("cart",{}),"from_storefront":from_storefront}
        return private_response(redirect("online_reservations:review" if from_storefront else "online_reservations:choice"))
    return private_response(render(request,"reservations/create.html",{"form":form,"step":"details",
        "storefront_cart_ready":bool(draft.get("from_storefront") and draft.get("cart")),**flow_context("undecided")}))


def flow_context(flow):
    return {"flow":flow,"details_url":reverse("online_reservations:create")}


@never_cache
def booking_details(request,flow):
    # Old bookmarks now share the single booking entry.
    if request.method=="POST":
        return create(request)
    return private_response(redirect("online_reservations:create"))


@never_cache
def preorder_choice(request):
    draft,details=draft_forms(request)
    if not details.is_valid():
        return private_response(redirect("online_reservations:create"))
    form=PreorderChoiceForm(request.POST if request.method=="POST" else None,
        initial={"mode":draft.get("details",{}).get("mode","TABLE")})
    if request.method=="POST" and form.is_valid():
        flow="preorder" if form.cleaned_data["decision"]=="yes" else "table"
        request.session["reservation_draft"]={**draft,"flow":flow,
            "details":{**draft["details"],"mode":form.cleaned_data["mode"]},
            "cart":draft.get("cart",{}) if flow=="preorder" else {}}
        return private_response(redirect("online_reservations:menu" if flow=="preorder" else "online_reservations:review"))
    return private_response(render(request,"reservations/choose.html",{"form":form,"details":details.cleaned_data,
        "step":"choice",**flow_context(draft.get("flow","undecided"))}))


def submit_legacy(request,policy):
    form=OnlineForm(request.POST)
    if form.is_valid():
        response=save_reservation(request,form)
        if response:
            return response
    flow="preorder" if request.POST.get("mode")=="READY" or any(request.POST.get(key) not in (None,"","0") for key in form.fields if key.startswith(("qty_","cqty_"))) else "table"
    request.session["reservation_draft"]={"flow":flow,"details":{key:request.POST.get(key,"") for key in ReservationDetailsForm().fields},
        "cart":{key:request.POST.get(key,"") for key in form.fields if key.startswith(("qty_","note_","cqty_","cnote_"))}}
    return private_response(render(request,"reservations/review.html",{**review_context(form,policy),**flow_context(flow)}))


def save_reservation(request,form):
    if form.is_valid():
        data=form.cleaned_data
        try:
            row=services.create_request(full_name=data["full_name"],phone=data["phone"],starts_at=data["starts_at"],party_size=data["party_size"],
                duration_minutes=data.get("duration_minutes") or form.default_minutes,mode=data["mode"],items=form.selected_items(),
                request_key=data["request_key"],source_digest=salted_hmac("reservation.source",request.session.session_key,algorithm="sha256").hexdigest(),
                area_id=data["area"].pk if data["area"] else None,note=data["note"])
        except ValidationError as error:
            form.add_error(None,error)
        else:
            request.session.pop("reservation_draft",None)
            remember_private_reservation(request,row)
            return private_response(redirect("online_reservations:detail",token=row.access_token))


def draft_forms(request):
    draft=request.session.get("reservation_draft",{})
    form=ReservationDetailsForm(draft.get("details",{}),booking_flow="table" if draft.get("flow")!="preorder" else None)
    return draft,form


@never_cache
def menu(request):
    draft,details=draft_forms(request)
    if not details.is_valid():
        messages.info(request,_("Vui lòng nhập lại thông tin đặt bàn trước khi chọn món."))
        return private_response(redirect("online_reservations:create"))
    if draft.get("flow")=="table":
        return private_response(redirect("online_reservations:review"))
    if draft.get("flow")=="undecided":
        return private_response(redirect("online_reservations:choice"))
    mode=details.cleaned_data["mode"]
    form=PreorderCartForm(request.POST if request.method=="POST" else draft.get("cart") or None,mode=mode)
    if request.method=="POST":
        valid=form.is_valid()
        # Keep quantities and notes, even when returning to fix the visit details.
        request.session["reservation_draft"]={**draft,"cart":{key:request.POST.get(key,"") for key in form.fields}}
        if request.POST.get("action")=="choice":
            return private_response(redirect("online_reservations:choice"))
        if request.POST.get("action")=="back":
            return private_response(redirect("online_reservations:create"))
        if valid:
            return private_response(redirect("online_reservations:review"))
    categories={row["dish"].category_id:row["dish"].category.name for row in form.item_rows}
    return private_response(render(request,"reservations/menu.html",{"form":form,"details":details.cleaned_data,"mode":mode,
        "categories":categories,"step":"menu",**flow_context("preorder")}))


def review_context(form,policy):
    # Bind on GET too so summaries use the same validation as final submission.
    form.is_valid()
    rows=[]
    for row in form.item_rows:
        quantity=form.cleaned_data.get(row["quantity"].name)
        if quantity:
            rows.append({**row,"count":quantity,"line_total":row["dish"].price*quantity,
                "item_note":form.cleaned_data.get(row["note"].name,"")})
    total=sum(row["line_total"] for row in rows)
    combo_rows=[]
    for row in form.combo_rows:
        quantity=form.cleaned_data.get(row["quantity"].name)
        if quantity:
            combo_rows.append({**row,"count":quantity,"line_total":row["combo"].price*quantity,
                "item_note":form.cleaned_data.get(row["note"].name,"")})
    total+=sum(row["line_total"] for row in combo_rows)
    return {"form":form,"policy":policy,"selected_rows":rows,"total":total,"step":"review","agree_checked":bool(form.cleaned_data.get("agree")),
        "details":form.cleaned_data,"selected_combos":combo_rows,"mode_label":dict(Reservation.Mode.choices).get(form.cleaned_data.get("mode"),"")}


@never_cache
def review(request):
    draft,details=draft_forms(request)
    if not details.is_valid():
        messages.info(request,_("Thông tin đặt bàn cần được kiểm tra lại."))
        return private_response(redirect("online_reservations:create"))
    flow=draft.get("flow","preorder")
    if flow=="undecided":
        return private_response(redirect("online_reservations:choice"))
    cart_data=draft.get("cart",{}) if flow=="preorder" else {}
    cart=PreorderCartForm(cart_data,mode=details.cleaned_data["mode"],require_items=flow=="preorder")
    if not cart.is_valid():
        messages.info(request,_("Vui lòng kiểm tra lại các món trong giỏ."))
        return private_response(redirect("online_reservations:menu"))
    data={**draft["details"],**cart_data,"mode":details.cleaned_data["mode"],
        "agree":request.POST.get("agree","") if request.method=="POST" else ""}
    form=OnlineForm(data)
    if request.method!="POST":
        form.fields["agree"].required=False
    if request.method=="POST" and form.is_valid():
        response=save_reservation(request,form)
        if response:
            return response
    context={**review_context(form,services.policy_snapshot()),**flow_context(flow)}
    return private_response(render(request,"reservations/review.html",context))


@never_cache
def lookup(request):
    form=LookupForm(request.POST or None)
    result=None
    reservation=None
    detail_url=None
    manage_url=None
    if request.method=="POST" and form.is_valid():
        code=form.cleaned_data["reservation_code"]
        if code.startswith("DB"):
            from apps.bookings.views import PublicReservationLookupView
            return PublicReservationLookupView.as_view()(request)
        services.expire_holds()
        row=Reservation.objects.select_related("booking__table").prefetch_related("items__order_item","deposits","refunds","allocations").filter(pk=int(code[2:]),phone=form.cleaned_data["phone"]).first()
        if row:
            # An unknown browser receives only general status. More details need
            # the original session, a previously visited capability, or staff ACL.
            result={"code":row.code,"status":row.get_status_display()}
            if owns_reservation(request,row):
                reservation=row
                detail_url=reverse("online_reservations:detail",args=[row.access_token])
            elif has_booking_permission(request.user,"manage_booking"):
                reservation=row
                manage_url=reverse("online_reservations:manage_detail",args=[row.pk])
        else:
            form.add_error(None,_("Không tìm thấy lịch khớp mã và số điện thoại."))
    return private_response(render(request,"reservations/lookup.html",{"form":form,"result":result,
        "reservation":reservation,"detail_url":detail_url,"manage_url":manage_url}))


def public_row(token):
    services.expire_holds()
    return get_object_or_404(Reservation.objects.select_related("booking__table").prefetch_related("items__dish","items__order_item","deposits","refunds","allocations"),access_token=token)


@never_cache
def detail(request,token):
    row=public_row(token)
    remember_private_reservation(request,row)
    if request.method=="POST":
        try:
            action=request.POST.get("action")
            if action=="accept":
                if request.POST.get("agree")!="yes":
                    raise ValidationError(_("Cần đồng ý bản chốt và điều kiện trước khi giữ chỗ."))
                services.accept_offer(token=token,revision=int(request.POST.get("revision","0")))
            elif action=="pay":
                if request.POST.get("agree")!="yes":
                    raise ValidationError(_("Cần đồng ý điều kiện thanh toán/hủy trước khi trả cọc."))
                payment,url=services.checkout(token=token,revision=int(request.POST.get("revision","0")),
                    return_url=request.build_absolute_uri(reverse("online_reservations:payment_return")),ip_address=request.META.get("REMOTE_ADDR"))
                return private_response(redirect(url))
            elif action in ("CHANGE","CANCEL"):
                services.customer_message(token=token,kind=action,text=request.POST.get("text",""))
                messages.success(request,_("Đã gửi yêu cầu. Nhà hàng cần xác minh trước khi thay đổi lịch/tiền cọc."))
            else:
                raise ValidationError(_("Thao tác không hợp lệ."))
        except ImproperlyConfigured:
            messages.error(request,_("Cổng thanh toán chưa sẵn sàng. Vui lòng liên hệ nhà hàng; không thanh toán lại nếu giao dịch trước chưa rõ kết quả."))
        except (ValidationError,ValueError) as error:
            error_message(request,error)
        return private_response(redirect("online_reservations:detail",token=token))
    from apps.orders.models import ZaloPayTransaction
    pending_zalopay=ZaloPayTransaction.objects.filter(deposit_payment__reservation=row,status="PENDING").first()
    remaining=(row.hold_expires_at-timezone.now()).total_seconds() if row.hold_expires_at else 0
    return private_response(render(request,"reservations/detail.html",{"reservation":row,
        "payment_ready":bool(settings.VNPAY_TMN_CODE and settings.VNPAY_HASH_SECRET),
        "zalopay_enabled":zalopay_enabled(),"zalopay_can_create":remaining>=MIN_EXPIRE_SECONDS,
        "zalopay_pending":pending_zalopay}))


@never_cache
@require_GET
def state(request,token):
    row=public_row(token)
    return private_response(JsonResponse({"status":row.status,"revision":row.revision,"received":str(row.received),"refunded":str(row.refunded),
        "updated_at":row.updated_at.isoformat()}))


@csrf_exempt
@require_GET
def ipn(request):
    code,message=services.deposit_ipn(request.GET.dict())
    return JsonResponse({"RspCode":code,"Message":message})


@never_cache
@require_GET
def payment_return(request):
    from apps.orders.vnpay import verify
    payment=DepositPayment.objects.select_related("reservation").filter(txn_ref=request.GET.get("vnp_TxnRef","")).first() if verify(request.GET.dict()) else None
    if payment:
        messages.info(request,_("Cổng thanh toán đã trả kết quả. Tiền cọc chỉ được xác nhận sau thông báo hợp lệ từ máy chủ VNPAY; hãy xem trạng thái bên dưới."))
        return private_response(redirect("online_reservations:detail",token=payment.reservation.access_token))
    return render(request,"reservations/return.html",status=400)


@staff
def manage(request):
    services.expire_holds()
    rows=Reservation.objects.select_related("booking__table").prefetch_related("deposits","refunds","allocations").all()
    state=request.GET.get("status","")
    if state in Reservation.Status.values:
        rows=rows.filter(status=state)
    from django.core.paginator import Paginator
    return render(request,"reservations/manage.html",{"page_obj":Paginator(rows,30).get_page(request.GET.get("page")),"statuses":Reservation.Status.choices})


@staff
@transaction.atomic
def manage_detail(request,pk):
    row=get_object_or_404(Reservation.objects.select_related("booking__table"),pk=pk)
    form=OfferForm(request.POST or None,reservation=row,initial={"revision":row.revision,"starts_at":row.starts_at,
        "prep_starts_at":row.prep_starts_at or row.starts_at-timedelta(minutes=30),"ready_by":row.ready_by or row.starts_at,"note":row.staff_note})
    if request.method=="POST":
        try:
            action=request.POST.get("action")
            revision=int(request.POST.get("revision","0"))
            if action=="offer":
                if not form.is_valid():
                    return render(request,"reservations/manage_detail.html",{"reservation":row,"form":form})
                fields={key:form.cleaned_data[key] for key in ("revision","starts_at","prep_starts_at","ready_by","note")}
                services.review_request(actor=request.user,reservation_id=pk,action="offer",items=form.selected_items(),**fields)
            elif action=="reject":
                services.review_request(actor=request.user,reservation_id=pk,revision=revision,action="reject",note=request.POST.get("reason",""))
            elif action=="receive":
                order=services.receive(actor=request.user,reservation_id=pk,revision=revision,accept_prices=request.POST.get("accept_prices")=="yes")
                return redirect(reverse("sales:workspace")+f"?order={order.pk}")
            elif action=="amend":
                if not form.is_valid():
                    return render(request,"reservations/manage_detail.html",{"reservation":row,"form":form})
                fields={key:form.cleaned_data[key] for key in ("revision","starts_at","prep_starts_at","ready_by","note")}
                services.amend_confirmed(actor=request.user,reservation_id=pk,items=form.selected_items(),verified=request.POST.get("verified")=="yes",**fields)
            elif action in ("cancel","no_show"):
                services.close_request(actor=request.user,reservation_id=pk,revision=revision,action=action,reason=request.POST.get("reason",""),verified=request.POST.get("verified")=="yes")
            elif action.startswith("refund_"):
                services.manage_refund(actor=request.user,reservation_id=pk,action=action[7:],amount=request.POST.get("amount","0"),reason=request.POST.get("reason",""),
                    refund_id=int(request.POST["refund_id"]) if request.POST.get("refund_id") else None,bank_reference=request.POST.get("bank_reference",""),verified=request.POST.get("verified")=="yes")
            elif action=="resolve_message":
                actor=services.actor_for(request.user)
                row.messages.filter(pk=int(request.POST.get("message_id","0"))).update(resolved=True)
                services.log(row,"Đã xử lý yêu cầu khách",request.POST.get("reason","")[:1000],actor)
            else:
                raise ValidationError(_("Thao tác không hợp lệ."))
        except (ValidationError,ValueError) as error:
            error_message(request,error)
        else:
            messages.success(request,_("Đã lưu xử lý yêu cầu."))
        return redirect("online_reservations:manage_detail",pk=pk)
    return render(request,"reservations/manage_detail.html",{"reservation":row,"form":form,
        "archived_items":PreorderItem._base_manager.filter(reservation=row,is_active=False)})


@login_required
@never_cache
def kitchen(request):
    if not has_order_permission(request.user,"work_kitchen"):
        raise PermissionDenied
    if request.method=="POST":
        try:
            services.kitchen_step(actor=request.user,item_id=int(request.POST.get("item_id","0")),target=request.POST.get("target"))
        except (ValidationError,ValueError) as error:
            error_message(request,error)
        return redirect("online_reservations:kitchen")
    rows=PreorderItem.objects.filter(reservation__status="CONFIRMED",order_item__isnull=True).exclude(status="CANCELLED").select_related("reservation__booking__table").prefetch_related("reservation__deposits").order_by("reservation__starts_at","reservation_id","pk")
    return render(request,"reservations/kitchen.html",{"items":rows,"now":timezone.now(),
        "can_manage_reservations":has_booking_permission(request.user,"manage_booking")})


@login_required
@never_cache
@transaction.atomic
def policy(request):
    if not can_manage_accounts(request.user):
        raise PermissionDenied
    row,policy_created=ReservationPolicy.objects.get_or_create(pk=1)
    form=PolicyForm(request.POST or None,instance=row)
    if request.method=="POST" and form.is_valid():
        actor=services.actor_for(request.user,"manager")
        form.save()
        from django.contrib.admin.models import LogEntry,CHANGE
        from django.contrib.contenttypes.models import ContentType
        LogEntry.objects.create(user=actor,content_type=ContentType.objects.get_for_model(ReservationPolicy),object_id=str(row.pk),
            object_repr="Chính sách đặt bàn/cọc",action_flag=CHANGE,change_message="Cập nhật chính sách và món cho phép chuẩn bị trước; yêu cầu cũ giữ snapshot.")
        messages.success(request,_("Đã lưu chính sách; các yêu cầu cũ giữ nguyên chính sách đã chốt."))
        return redirect("online_reservations:policy")
    return render(request,"reservations/policy.html",{"form":form})
