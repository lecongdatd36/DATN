"""Real guest/staff UI against a disposable DB and a LOCAL payment fixture.

No real banking request or real customer data. Signed IPN handling and ledger
are the real application; only the bank and wall clock are test fixtures.
"""
from datetime import timedelta
import json,mimetypes,os,subprocess,sys,tempfile,threading
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4
from unittest.mock import patch
from wsgiref.simple_server import make_server,WSGIRequestHandler,WSGIServer
from socketserver import ThreadingMixIn
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE));sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE","QLNH.test_settings")
import django
django.setup()
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.db import connection,connections
from django.test import Client,override_settings
from django.test.runner import DiscoverRunner
from django.urls import reverse
from apps.reservations.tests.test_reservations import ReservationTests
from apps.reservations.models import Reservation,DepositPayment,IngredientHold
from apps.orders.models import Order,OrderItem
from apps.seating.models import DiningTable
from apps.menu.models import Dish


class Quiet(WSGIRequestHandler):
    def log_message(self,*args):pass


class Server(ThreadingMixIn,WSGIServer):
    daemon_threads=True


def main():
    connection.settings_dict["TEST"]["NAME"]="test_qlnh_reservations_ui_"+uuid4().hex
    runner=DiscoverRunner(verbosity=0,interactive=False)
    old=runner.setup_databases();server=None
    try:
        connection.settings_dict["CONN_MAX_AGE"]=0
        ReservationTests.setUpTestData()
        fixture=ReservationTests()
        # Use known food photos for visual QA, never an arbitrary uploaded file.
        photo=BASE/"media/dishes/330d9de069394270aea48f8996251e48-main.webp"
        if photo.is_file():
            Dish.objects.filter(pk=fixture.dish.pk).update(name="Bún chả Hà Nội",image="dishes/"+photo.name)
        for index,(name,filename) in enumerate([
            ("Rau củ luộc kho quẹt","40cc4df306e54405a70a0a751978ba41-main.webp"),
            ("Trà chanh","5cce8170d6d3487d924587388eff47b1-main.webp"),
            ("Chè khúc bạch","f56e55d0fb3b4074b535ad94ea59c9aa-main.webp"),
        ]):
            if (BASE/"media/dishes"/filename).is_file():
                Dish.objects.create(code=f"VISUAL{index}",name=name,category=fixture.category,unit=fixture.unit,
                    price=50000,image="dishes/"+filename)
        DiningTable.objects.create(code="OL02",area=fixture.area,capacity=8)
        clock={"now":fixture.now}
        with patch("django.utils.timezone.now",side_effect=lambda:clock["now"]):
            client=Client();client.force_login(fixture.manager)
            session=client.cookies[settings.SESSION_COOKIE_NAME].value
            application=get_wsgi_application()
            config={"dish":fixture.dish.pk,"arrival":fixture.arrival.strftime("%Y-%m-%dT%H:%M"),"prep":(fixture.arrival-timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")}
            def respond(start,data,content_type="text/html; charset=utf-8",headers=None,status="200 OK"):
                data=data.encode() if isinstance(data,str) else data
                start(status,[("Content-Type",content_type),("Content-Length",str(len(data))),*(headers or [])]);return [data]
            def app(environ,start):
                path=environ.get("PATH_INFO","")
                query=parse_qs(environ.get("QUERY_STRING",""))
                if path=="/__reservation_test__/config":
                    return respond(start,json.dumps(config),"application/json")
                if path=="/__reservation_test__/login":
                    return respond(start,"",headers=[("Set-Cookie",f"{settings.SESSION_COOKIE_NAME}={session}; Path=/; HttpOnly; SameSite=Lax"),("Location",reverse("online_reservations:manage"))],status="302 Found")
                if path=="/__reservation_test__/clock" and environ.get("REQUEST_METHOD")=="POST":
                    clock["now"]=fixture.arrival-timedelta(minutes=30) if query.get("at")==["prep"] else fixture.arrival
                    return respond(start,"OK")
                if path=="/__reservation_test__/bank":
                    ref=query.get("vnp_TxnRef",[""])[0]
                    payment=DepositPayment.objects.get(txn_ref=ref)
                    connections.close_all()
                    return respond(start,f'<h1>Bank fixture — no real payment</h1><form method="post" action="/__reservation_test__/confirm?ref={payment.txn_ref}"><button id="confirm-fixture">Send signed success IPN</button></form>')
                if path=="/__reservation_test__/confirm" and environ.get("REQUEST_METHOD")=="POST":
                    payment=DepositPayment.objects.select_related("reservation").get(txn_ref=query["ref"][0])
                    result=Client().get(reverse("online_reservations:ipn"),fixture.callback(payment)).json()
                    if result["RspCode"]!="00":
                        raise RuntimeError(result)
                    target=reverse("online_reservations:detail",args=[payment.reservation.access_token])
                    connections.close_all()
                    return respond(start,"",headers=[("Location",target)],status="302 Found")
                if path.startswith("/static/"):
                    root=Path(settings.STATIC_ROOT).resolve();target=(root/path.removeprefix("/static/")).resolve()
                    if target.is_relative_to(root) and target.is_file():
                        return respond(start,target.read_bytes(),mimetypes.guess_type(target)[0] or "application/octet-stream")
                    return respond(start,"",status="404 Not Found")
                if path.startswith("/media/"):
                    root=Path(settings.MEDIA_ROOT).resolve();target=(root/path.removeprefix("/media/")).resolve()
                    if target.is_relative_to(root) and target.is_file():
                        return respond(start,target.read_bytes(),mimetypes.guess_type(target)[0] or "application/octet-stream")
                    return respond(start,"",status="404 Not Found")
                return application(environ,start)
            server=make_server("127.0.0.1",0,app,server_class=Server,handler_class=Quiet)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            base=f"http://127.0.0.1:{server.server_port}"
            output=BASE/"artifacts/reservations/browser";output.mkdir(parents=True,exist_ok=True)
            with override_settings(VNPAY_PAYMENT_URL=base+"/__reservation_test__/bank"),tempfile.TemporaryDirectory(prefix="qlnh-reservation-ui-",ignore_cleanup_errors=True) as profile:
                result=subprocess.run(["node",str(BASE/"scripts/run_reservations_chrome.cjs"),base,profile,str(output)],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=150,
                    env={key:value for key,value in os.environ.items() if key.upper() in {"SYSTEMROOT","WINDIR","TEMP","TMP","PATH","USERPROFILE","LOCALAPPDATA","APPDATA","COMSPEC"}})
                print(result.stdout or result.stderr)
                if result.returncode:raise RuntimeError("Reservation browser checks failed")
            fixture.ingredient.refresh_from_db()
            assert fixture.ingredient.stock_quantity==9
            assert Reservation.objects.count()==2 and DepositPayment.objects.filter(status="PAID").count()==2
            assert Order.objects.count()==1 and OrderItem.objects.count()==1
            assert OrderItem.objects.get().status=="READY"
            assert IngredientHold.objects.filter(state="CONSUMED").count()==1
            print("Guest A/B forms, staff offer, guest consent, signed local payment fixture, prep and receive verified; one stock deduction.")
    finally:
        if server:server.shutdown();server.server_close()
        connections.close_all();runner.teardown_databases(old)


if __name__=="__main__":
    with override_settings(DEBUG=True,ALLOWED_HOSTS=["127.0.0.1","localhost","testserver"],SECURE_SSL_REDIRECT=False,
        SESSION_COOKIE_SECURE=False,CSRF_COOKIE_SECURE=False,VNPAY_TMN_CODE="TESTCODE",VNPAY_HASH_SECRET="test-only-deposit-secret",
        STORAGES={**settings.STORAGES,"default":{"BACKEND":"django.core.files.storage.FileSystemStorage"}}):
        main()
