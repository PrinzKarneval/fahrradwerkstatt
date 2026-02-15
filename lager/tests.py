from decimal import Decimal

from django.test import TestCase
from django.core.exceptions import PermissionDenied, ValidationError

from werkstatt.models import RepairOrder, RepairOrderArticle, StockArticleReservation, StockArticleRequest, Customer
from werkstatt.services import InvoiceCreationService, RepairOrderHandler
from .models import StockMovement, Manufacturer, Article, ArticleType, StockArticle, MovementType
from .services import StockService, DemandService


class StockMovementTest(TestCase):
    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(name='Manufacturer')
        self.article_type = ArticleType.objects.create(name='Article Type')
        self.article = Article.objects.create(
            manufacturer=self.manufacturer,
            type=self.article_type,
            name='Article',
            ean='123456789',
            price=Decimal('100.00'),
        )
        self.stock_article = StockArticle.objects.create(
            article=self.article,
            price=Decimal('50.00'),
        )
        self.stock_movement = StockMovement.objects.create(
            stock_article=self.stock_article,
            quantity=1,
            price=self.stock_article.price,
            movement_type=MovementType.IN_DELIVERY,
            reference='Delivery 1'
        )

    def test_delete_raises_permission_denied(self):
        self.assertRaises(PermissionDenied, self.stock_movement.delete)

    def test_instance_still_exists_after_delete_attempt(self):
        try:
            self.stock_movement.delete()
        except PermissionDenied:
            pass
        self.assertTrue(StockMovement.objects.filter(id=self.stock_movement.id).exists())

    def test_reduce_available_stock(self):
        StockMovement.objects.create(
            stock_article=self.stock_article,
            quantity=1,
            price=self.stock_article.price,
            movement_type=MovementType.OUT_SOLD,
            reference='Verkauft'
        )


class StockServiceTest(TestCase):
    def setUp(self):
        self.article = StockArticle.objects.create(article_id=1, price=Decimal("100.00"))
        # Add initial stock via StockMovement
        StockMovement.objects.create(
            stock_article=self.article,
            quantity=10,
            price=self.article.price,
            movement_type=MovementType.IN_DELIVERY,
            reference="Initial Stock"
        )

    def test_create_in_movement(self):
        StockService.create_movement(
            stock_article=self.article,
            quantity=5,
            movement_type=MovementType.IN_DELIVERY,
            reference="Test IN"
        )
        movement = StockMovement.objects.filter(stock_article=self.article,
                                                movement_type=MovementType.IN_DELIVERY).last()
        self.assertEqual(movement.quantity, 5)
        # Check available quantity increased
        self.assertEqual(self.article.get_available_quantity(), 15)

    def test_create_out_movement_with_insufficient_stock(self):
        with self.assertRaises(ValidationError):
            StockService.create_movement(
                stock_article=self.article,
                quantity=20,
                movement_type=MovementType.OUT_SOLD,
                reference="Test OUT"
            )

    def test_create_out_movement_with_available_stock(self):
        StockService.create_movement(
            stock_article=self.article,
            quantity=5,
            movement_type=MovementType.OUT_SOLD,
            reference="Test OUT"
        )
        movement = StockMovement.objects.filter(stock_article=self.article, movement_type=MovementType.OUT_SOLD).last()
        self.assertEqual(movement.quantity, 5)
        # Check available quantity decreased
        self.assertEqual(self.article.get_available_quantity(), 5)


class DemandServiceTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Test Customer",
            postal="12345",
            city="Test City",
            street="Test Street",
            str_no="1"
        )
        self.article = StockArticle.objects.create(article_id=1, price=Decimal("50.00"))
        StockMovement.objects.create(
            stock_article=self.article,
            quantity=10,
            price=self.article.price,
            movement_type=MovementType.IN_DELIVERY,
            reference="Initial Stock"
        )
        self.order = RepairOrder.objects.create(customer=self.customer, description="Test order")
        self.roa = RepairOrderArticle.objects.create(order=self.order, stock_article=self.article, quantity=5)

    def test_sync_repair_order_article_creates_request_and_reservation(self):
        DemandService.sync_repair_order_article(self.roa)
        reservation = StockArticleReservation.objects.filter(repair_order_article=self.roa).first()
        request = StockArticleRequest.objects.filter(repair_order_article=self.roa).first()
        self.assertIsNotNone(reservation)
        self.assertEqual(reservation.quantity, 5)
        self.assertIsNone(request)

    def test_update_demands_allocates_stock(self):
        # Create a request larger than stock
        StockArticleRequest.objects.create(repair_order_article=self.roa, stock_article=self.article, quantity=15)
        DemandService.update_demands([self.article])
        reservation = StockArticleReservation.objects.filter(repair_order_article=self.roa).first()
        request = StockArticleRequest.objects.filter(repair_order_article=self.roa).first()
        self.assertEqual(reservation.quantity, 5)
        self.assertEqual(request.quantity, 10)  # Remaining unfulfilled request


class RepairOrderHandlerTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Test Customer",
            postal="12345",
            city="Test City",
            street="Test Street",
            str_no="1"
        )

        self.article = StockArticle.objects.create(article_id=1, price=Decimal("100.00"))
        StockMovement.objects.create(
            stock_article=self.article,
            quantity=10,
            price=self.article.price,
            movement_type=MovementType.IN_DELIVERY,
            reference="Initial Stock"
        )
        self.order = RepairOrder.objects.create(customer=self.customer, description="Test RO")

    def test_update_quantity_creates_roa_and_reservation(self):
        RepairOrderHandler.update_quantity(self.order, self.article, 5)
        roa = RepairOrderArticle.objects.get(order=self.order, stock_article=self.article)
        reservation = StockArticleReservation.objects.get(repair_order_article=roa)
        self.assertEqual(roa.quantity, 5)
        self.assertEqual(reservation.quantity, 5)

    def test_update_quantity_zero_deletes_roa(self):
        RepairOrderHandler.update_quantity(self.order, self.article, 0)
        self.assertFalse(RepairOrderArticle.objects.filter(order=self.order).exists())


class InvoiceCreationServiceTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Test Customer",
            postal="12345",
            city="Test City",
            street="Test Street",
            str_no="1"
        )
        self.article = StockArticle.objects.create(article_id=1, price=Decimal("100.00"))
        StockMovement.objects.create(
            stock_article=self.article,
            quantity=10,
            price=self.article.price,
            movement_type=MovementType.IN_DELIVERY,
            reference="Initial Stock"
        )
        self.order = RepairOrder.objects.create(customer=self.customer, description="Test RO")
        self.roa = RepairOrderArticle.objects.create(order=self.order, stock_article=self.article, quantity=5)
        StockArticleReservation.objects.create(repair_order_article=self.roa, stock_article=self.article, quantity=5)

    def test_create_invoice_consumes_reserved_stock(self):
        invoice = InvoiceCreationService.create_invoice(self.order)
        self.assertEqual(invoice.articles.first().quantity, 5)
        # Check available quantity decreased
        self.assertEqual(self.article.get_available_quantity(), 5)
        self.assertFalse(RepairOrderArticle.objects.filter(order=self.order).exists())

    def test_create_invoice_fails_with_open_requests(self):
        StockArticleRequest.objects.create(repair_order_article=self.roa, stock_article=self.article, quantity=1)
        with self.assertRaises(ValidationError):
            InvoiceCreationService.create_invoice(self.order)
