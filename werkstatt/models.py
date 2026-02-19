from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from lager.models import decimal_field_default, ArticleType, StockArticle, Manufacturer


class Customer(models.Model):
    name = models.CharField(max_length=100, verbose_name='Name')
    email = models.EmailField(blank=True, null=True, verbose_name='Email')
    phone = models.CharField(max_length=25, blank=True, null=True, verbose_name='Telefon')
    postal = models.CharField(max_length=5, verbose_name='PLZ')
    city = models.CharField(max_length=50, default='Nürnberg', verbose_name='Ort')
    street = models.CharField(max_length=100, verbose_name='Straße')
    str_no = models.CharField(max_length=20, verbose_name='Nr.')

    class Meta:
        verbose_name = 'Kunde'
        verbose_name_plural = 'Kunden'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('customer_detail', kwargs={'pk': self.pk})

    def get_open_repairs(self):
        return self.orders.filter(date_finished__isnull=True).count()


class RepairOrder(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders')
    date_created = models.DateTimeField(auto_now_add=True)
    date_finished = models.DateTimeField(blank=True, null=True)
    description = models.TextField(blank=True)
    is_ebike = models.BooleanField(default=False)
    manufacturer = models.CharField(max_length=100, verbose_name='Hersteller')
    bike_model = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=30, blank=True, null=True)
    serial_number = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = 'Reparaturauftrag'
        verbose_name_plural = 'Reparaturaufträge'
        ordering = ['-date_created']

    def __str__(self):
        return f'RO #{self.pk} - {self.customer}'

    def get_absolute_url(self):
        return reverse('repair_order_detail', kwargs={'pk': self.pk})

    def get_total_articles_price(self):
        return sum(roa.get_total() for roa in self.articles.select_related("stock_article__article"))

    def get_total_services_price(self):
        return sum(ros.get_total() for ros in self.services.all())

    def get_total_price(self) -> Decimal:
        return (self.get_total_articles_price() + self.get_total_services_price()).quantize(Decimal('0.01'))


class RepairOrderArticle(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name='articles')
    stock_article = models.ForeignKey(StockArticle, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = 'Artikel im Reparaturauftrag'
        verbose_name_plural = 'Artikel im Reparaturauftrag'

    def __str__(self):
        return f'{self.stock_article} x {self.quantity}'

    def get_total(self) -> Decimal:
        return self.stock_article.article.price * self.quantity

    def get_reservations_quantity(self):
        return self.reservations.aggregate(quantity=Coalesce(models.Sum('quantity'), 0))['quantity']

    def get_missing_reservation_quantity(self):
        return self.quantity - self.get_reservations_quantity()

    def all_reserved(self):
        return self.get_reservations_quantity() >= self.quantity


class ServiceCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name='Name')

    class Meta:
        ordering = ['name']
        verbose_name = 'Servicekategorie'
        verbose_name_plural = 'Servicekategorien'

    def __str__(self):
        return self.name


class AbstractService(models.Model):
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name='services')
    number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    normal_price = decimal_field_default()
    ebike_price = decimal_field_default()

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return self.name


class Service(AbstractService):
    class Meta:
        verbose_name = 'Service'
        verbose_name_plural = 'Services'


class RepairOrderService(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name='services')
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = 'Service im Reparaturauftrag'
        verbose_name_plural = 'Services im Reparaturauftrag'

    def __str__(self):
        return f'{self.service.name} x {self.quantity}'

    def get_total(self) -> Decimal:
        if self.order.is_ebike:
            return self.service.ebike_price * self.quantity
        return self.service.normal_price * self.quantity



class StockArticleReservation(models.Model):
    repair_order_article = models.ForeignKey(RepairOrderArticle, on_delete=models.CASCADE, related_name='reservations')
    stock_article = models.ForeignKey(StockArticle, on_delete=models.CASCADE, related_name='reservations')
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['repair_order_article', 'stock_article'], name='unique_reservation_roa_and_sa'),
        ]
        verbose_name = 'Reservierter Lagerartikel'
        verbose_name_plural = 'Reservierte Lagerartikel'

    def __str__(self):
        return f'{self.stock_article} reserviert für {self.repair_order_article} ({self.quantity})'


class StockArticleRequest(models.Model):
    repair_order_article = models.ForeignKey(RepairOrderArticle, on_delete=models.CASCADE, related_name='requests')
    stock_article = models.ForeignKey(StockArticle, on_delete=models.CASCADE, related_name='requests')
    quantity = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['repair_order_article', 'stock_article'], name='unique_request_roa_and_sa'),
        ]
        ordering = ['created']
        verbose_name = 'Angeforderter Lagerartikel'
        verbose_name_plural = 'Angeforderte Lagerartikel'

    def __str__(self):
        return f'{self.stock_article} angefordert für {self.repair_order_article} ({self.quantity})'


class WorkRate(models.Model):
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('50.00'),
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
        if not current:
            raise ValidationError('Arbeitswertsatz ist nicht gefunden.')
        return current.rate

    def __str__(self):
        return f'{self.rate} €/h ab {self.start_date}'


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
        return f'Rechnung #{self.pk} - {self.customer}'


class InvoiceArticle(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='articles')
    stock_article = models.ForeignKey(StockArticle, null=True, on_delete=models.SET_NULL)
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.PROTECT)
    type = models.ForeignKey(ArticleType, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ean = models.CharField(max_length=13, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'),
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
