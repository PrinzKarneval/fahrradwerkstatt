from django.test import TestCase

from lager.models import *
from lager.services import DeliveryService

manufacturer = {"name": 'Hersteller'}
article_type = {"name": 'Artikeltyp 1'}
article1 = {
    "name": "Artikel 1",
    "description": "",
    "ean": "123",
    "price": Decimal('100.00'),
}
vendor = {
    "name": "Vendor 1",
    "postal": "12345",
    "city": "City",
    "street": "Street",
    "str_no": "1"
}
delivery = {
    "delivery_number": "2026-01",
    "delivery_date": timezone.now().date(),
}
delivery_article1 = {
}


class DeliveryServiceTest(TestCase):
    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(**manufacturer)
        self.article_type = ArticleType.objects.create(**article_type)
        self.article = Article.objects.create(
            manufacturer=self.manufacturer,
            type=self.article_type,
            **article1)
        self.vendor = Vendor.objects.create(**vendor)
        self.delivery0 = Delivery.objects.create(vendor=self.vendor, **delivery)
        self.delivery1 = Delivery.objects.create(vendor=self.vendor, **delivery)
        self.delivery2 = Delivery.objects.create(vendor=self.vendor, **delivery)
        self.delivery3 = Delivery.objects.create(vendor=self.vendor, is_correction=True, **delivery)
        self.delivery4 = Delivery.objects.create(vendor=self.vendor, is_correction=True, **delivery)
        self.delivery_article1 = DeliveryArticle.objects.create(
            delivery=self.delivery1,
            article=self.article,
            quantity=2,
            price=Decimal('50.00')
        )
        self.delivery_article2 = DeliveryArticle.objects.create(
            delivery=self.delivery2,
            article=self.article,
            quantity=2,
            price=Decimal('50.00')
        )
        self.delivery_article3 = DeliveryArticle.objects.create(
            delivery=self.delivery3,
            article=self.article,
            quantity=1,
            price=Decimal('50.00')
        )
        self.delivery_article4 = DeliveryArticle.objects.create(
            delivery=self.delivery4,
            article=self.article,
            quantity=2,
            price=Decimal('9.99')
        )

    def test_check_in_delivery_without_articles(self):
        with self.assertRaises(ValidationError):
            DeliveryService.check_in_delivery(self.delivery0)

    def test_check_in_delivery(self):
        DeliveryService.check_in_delivery(self.delivery1)
        sa = StockArticle.objects.get(article=self.article, price=50)
        self.assertEqual(sa.quantity, 2)
        DeliveryService.check_in_delivery(self.delivery2)
        self.assertEqual(sa.quantity, 4)
        self.assertEqual(StockMovement.objects.count(), 2)
        self.assertEqual(sum(sm.quantity for sm in StockMovement.objects.all()), 4)

    def test_correction(self):
        DeliveryService.check_in_delivery(self.delivery1)
        sa = StockArticle.objects.get(article=self.article, price=50)
        self.assertEqual(sa.quantity, 2)
        DeliveryService.check_in_delivery(self.delivery3)
        self.assertEqual(sa.quantity, 1)

    def test_correction_with_wrong_sa(self):
        DeliveryService.check_in_delivery(self.delivery1)
        sa = StockArticle.objects.get(article=self.article, price=50)
        self.assertEqual(sa.quantity, 2)
        with self.assertRaises(ValidationError):
            DeliveryService.check_in_delivery(self.delivery4)


class StockMovementTestCase(TestCase):
    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(**manufacturer)
        self.article_type = ArticleType.objects.create(**article_type)
        self.article = Article.objects.create(**article1)
        self.delivery = Delivery.objects.create(**delivery)
