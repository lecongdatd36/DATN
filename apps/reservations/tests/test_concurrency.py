from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import connections
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase,override_settings
from apps.reservations.models import Reservation,DepositPayment
from apps.reservations import services
from .test_reservations import ReservationTests


@override_settings(VNPAY_TMN_CODE="TESTCODE",VNPAY_HASH_SECRET="test-only-deposit-secret")
class OnlineConcurrencyTests(TransactionTestCase):
    serialized_rollback=True
    at=ReservationTests.at
    create_row=ReservationTests.create_row
    callback=ReservationTests.callback

    def setUp(self):
        ReservationTests.setUpTestData.__func__(type(self))

    def race(self,operation):
        barrier=Barrier(2)
        def worker(index):
            try:
                barrier.wait(timeout=10)
                return operation(index)
            except ValidationError:
                return "rejected"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(worker,range(2)))

    def test_concurrent_holds_do_not_double_book_one_table(self):
        with self.at(self.now):
            results=self.race(lambda index:self.create_row().status)
        self.assertCountEqual(results,["WAITING","rejected"])
        self.assertEqual(Reservation.objects.count(),1)

    def test_concurrent_callback_receives_money_once(self):
        with self.at(self.now):
            row=self.create_row()
            payment,_=services.checkout(token=row.access_token,revision=row.revision,return_url="https://test/",ip_address="127.0.0.1")
            params=self.callback(payment)
            results=self.race(lambda index:services.deposit_ipn(params)[0])
        self.assertCountEqual(results,["00","02"])
        self.assertEqual(DepositPayment.objects.filter(status="PAID").count(),1)
        self.assertEqual(row.received,100000)
