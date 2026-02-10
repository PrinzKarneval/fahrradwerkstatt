from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from lager.models import decimal_field_default, ArticleType, StockArticle, Service, Manufacturer

BIKE_TYPES = (
    ('children_bike', "Children's bike"),
    ('hub_gear', 'Hub Gear'),
    ('derailleur', 'Derailleur'),
    ('mtb', 'MTB'),
    ('road_bike', 'Road Bike'),
)


class Customer(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)
    postal = models.CharField(max_length=5)
    city = models.CharField(max_length=50, default="Nürnberg")
    street = models.CharField(max_length=100)
    str_no = models.CharField(max_length=20)

    class Meta:
        verbose_name = 'Kunde'
        verbose_name_plural = 'Kunden'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("customer_detail", kwargs={"pk": self.pk})


class RepairOrder(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    date_created = models.DateTimeField(auto_now_add=True)
    date_finished = models.DateTimeField(blank=True, null=True)
    description = models.TextField(blank=True)
    bike_type = models.CharField(max_length=50, blank=True, null=True)
    bike_model = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=30, blank=True, null=True)
    serial_number = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = 'Reparaturauftrag'
        verbose_name_plural = 'Reparaturaufträge'
        ordering = ['-date_created']

    def __str__(self):
        return f"RO #{self.pk} - {self.customer}"

    def get_absolute_url(self):
        return reverse("repair_order_detail", kwargs={"pk": self.pk})

    def get_total_article_price(self):
        return sum((a.stock_article.article.price or 0) * a.quantity for a in self.articles.all())


class RepairOrderArticle(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name='articles')
    stock_article = models.ForeignKey(StockArticle, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = 'Artikel im Reparaturauftrag'
        verbose_name_plural = 'Artikel im Reparaturauftrag'

    def __str__(self):
        return f"{self.stock_article} x {self.quantity}"


class RepairOrderService(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name='services')
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = 'Service im Reparaturauftrag'
        verbose_name_plural = 'Services im Reparaturauftrag'

    def __str__(self):
        return f"{self.service.name} x {self.quantity}"

    def get_work_value(self):
        return self.service.get_work_value_for_type(self.order.bike_type)


class StockArticleReservation(models.Model):
    repair_order_article = models.ForeignKey(RepairOrderArticle, on_delete=models.CASCADE, related_name='reservations')
    stock_article = models.ForeignKey(StockArticle, on_delete=models.CASCADE, related_name='reservations')
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Reservierter Lagerartikel'
        verbose_name_plural = 'Reservierte Lagerartikel'

    def __str__(self):
        return f"{self.stock_article} reserviert für {self.repair_order_article} ({self.quantity})"


class StockArticleRequest(models.Model):
    repair_order_article = models.ForeignKey(RepairOrderArticle, on_delete=models.CASCADE, related_name='requests')
    stock_article = models.ForeignKey(StockArticle, on_delete=models.CASCADE, related_name='requests')
    quantity = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Angeforderter Lagerartikel'
        verbose_name_plural = 'Angeforderte Lagerartikel'
        ordering = ['created']

    def __str__(self):
        return f"{self.stock_article} angefordert für {self.repair_order_article} ({self.quantity})"


class WorkRate(models.Model):
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("50.00"),
                               validators=[MinValueValidator(0)])
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(blank=True, null=True)

    class Meta:
        verbose_name = 'Arbeitswertsatz'
        verbose_name_plural = 'Arbeitswertsätze'
        ordering = ['-start_date']

    @staticmethod
    def get_current_rate() -> Decimal:
        current = WorkRate.objects.filter(
            start_date__lte=timezone.now(),
        ).order_by('-start_date').first()
        return current.rate if current else Decimal("50.00")

    def __str__(self):
        return f"{self.rate} €/h ab {self.start_date}"


class Invoice(models.Model):
    date_paid = models.DateTimeField(default=timezone.now)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    postal = models.CharField(max_length=5)
    city = models.CharField(max_length=50)
    street = models.CharField(max_length=100)
    str_no = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    bike_type = models.CharField(max_length=50, blank=True, null=True)
    bike_model = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=30, blank=True, null=True)
    serial_number = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        ordering = ['-date_paid']
        verbose_name = 'Rechnung'
        verbose_name_plural = 'Rechnungen'

    def __str__(self):
        return f"Rechnung #{self.pk} - {self.customer}"


class InvoiceArticle(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='articles')
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.PROTECT)
    type = models.ForeignKey(ArticleType, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ean = models.CharField(max_length=13, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"),
                                validators=[MinValueValidator(0)])
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Rechnungsartikel'
        verbose_name_plural = 'Rechnungsartikel'

    def total(self) -> Decimal:
        return self.price * self.quantity


class InvoiceService(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='services')
    main_category = models.CharField(max_length=100)
    sub_category = models.CharField(max_length=100, blank=True, null=True)
    number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    children_bike = decimal_field_default()
    hub_gear = decimal_field_default()
    derailleur = decimal_field_default()
    mtb = decimal_field_default()
    road_bike = decimal_field_default()
    cargo_bike = decimal_field_default()
    hub_engine = decimal_field_default()
    mid_engine = decimal_field_default()
    price = decimal_field_default()
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Rechnungsservice'
        verbose_name_plural = 'Rechnungsservices'

    def total(self) -> Decimal:
        return self.price * self.quantity
