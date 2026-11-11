"""Local-only payment return QA with signed callbacks and a disposable database."""
import json, mimetypes, os, subprocess, sys, tempfile, threading
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from socketserver import ThreadingMixIn
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','QLNH.test_settings')
import django
django.setup()
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.wsgi import get_wsgi_application
from django.db import connection, connections
from django.test import Client, override_settings
from django.test.runner import DiscoverRunner
from django.urls import reverse
from apps.orders import zalopay_services
from apps.orders.models import Invoice, Payment
from apps.orders.tests.test_zalopay import ZaloPayOrderTests, SANDBOX, receipt

class Server(ThreadingMixIn,WSGIServer): daemon_threads=True
class Quiet(WSGIRequestHandler):
    def log_message(self,*args):pass

def main():
    if connection.settings_dict['HOST'] not in ('localhost','127.0.0.1','::1'):raise RuntimeError('Local database only')
    name='test_zalopay_return_'+uuid4().hex
    connection.settings_dict['TEST']['NAME']=name
    runner=DiscoverRunner(verbosity=0,interactive=False)
    old=runner.setup_databases();server=None
    try:
        connection.settings_dict['CONN_MAX_AGE']=0
        ZaloPayOrderTests.setUpTestData()
        fixture=ZaloPayOrderTests()
        order=fixture.ready_order_for_payment()
        with patch('apps.orders.zalopay.post',return_value={'return_code':1,'order_url':'https://qcgateway.zalopay.vn/pay?order=fixture'}):
            row=zalopay_services.create_order_payment(actor=fixture.users['CASHIER'],order_id=order.pk,base_url='http://localhost')
        cashier=Client();cashier.force_login(fixture.users['CASHIER'])
        cookie=cashier.cookies[settings.SESSION_COOKIE_NAME].value
        application=get_wsgi_application()
        def respond(start,body='',content_type='text/html; charset=utf-8',headers=None,status='200 OK'):
            body=body.encode('utf-8') if isinstance(body,str) else body
            start(status,[('Content-Type',content_type),('Content-Length',str(len(body))),*(headers or [])]);return [body]
        def app(environ,start):
            path=environ.get('PATH_INFO','')
            if path=='/__payment_test__/login':
                return respond(start,headers=[('Set-Cookie',f'{settings.SESSION_COOKIE_NAME}={cookie}; Path=/; HttpOnly; SameSite=Lax'),('Location',reverse('zalopay:result',args=[row.token]))],status='302 Found')
            if path=='/__payment_test__/config':return respond(start,json.dumps({'result':reverse('zalopay:result',args=[row.token]),'order':order.pk}),'application/json')
            if path=='/__payment_test__/confirm' and environ.get('REQUEST_METHOD')=='POST':
                result=Client().post(reverse('zalopay:callback'),receipt(row),content_type='application/json')
                assert result.json()['return_code']==1
                connections.close_all();return respond(start,'OK')
            if path.startswith('/static/'):
                target=finders.find(path.removeprefix('/static/'))
                if target and Path(target).is_file():return respond(start,Path(target).read_bytes(),mimetypes.guess_type(target)[0] or 'application/octet-stream')
            result=list(application(environ,start));connections.close_all();return result
        server=make_server('127.0.0.1',0,app,server_class=Server,handler_class=Quiet)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        output=ROOT/'artifacts/homepage-preview/payment-return';output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='cq-payment-return-',ignore_cleanup_errors=True) as profile, patch('apps.orders.zalopay.post',return_value={'return_code':3,'is_processing':True}):
            result=subprocess.run(['node',str(ROOT/'scripts/run_zalopay_return_chrome.cjs'),f'http://127.0.0.1:{server.server_port}',profile,str(output)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=70)
            print(result.stdout or result.stderr)
            if result.returncode:raise RuntimeError('Payment return browser checks failed')
        assert Invoice.objects.filter(status='PAID').count()==1
        assert Payment.objects.count()==1
        print('Exactly one invoice/payment from a signed local fixture callback. No external payment request or real data used.')
    finally:
        if server:server.shutdown();server.server_close()
        connections.close_all()
        with connection._nodb_cursor() as cursor:cursor.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()',[name])
        runner.teardown_databases(old)

if __name__=='__main__':
    with override_settings(**SANDBOX,DEBUG=True,ALLOWED_HOSTS=['127.0.0.1','localhost','testserver'],SECURE_SSL_REDIRECT=False,SESSION_COOKIE_SECURE=False,CSRF_COOKIE_SECURE=False):main()
