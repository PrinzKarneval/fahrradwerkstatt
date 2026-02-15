from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from lager.models import decimal_field_default, ArticleType, StockArticle, Manufacturer, MovementType, ZERO_DECIMAL, \
    STOCK_IN
from werkstatt.services import RepairOrderPricingService

BIKE_TYPES = (
    ('children_bike', 'Children\'s bike'),
    ('hub_gear', 'Hub Gear'),
    ('derailleur', 'Derailleur'),
    ('mtb', 'MTB'),
    ('road_bike', 'Road Bike'),
)


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
    bike_type = models.CharField(choices=BIKE_TYPES, max_length=20, default='derailleur')
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
        return sum([roa.get_total() for roa in self.articles.all()])

    def get_total_services_price(self):
        return RepairOrderPricingService.get_total_services_price(self)

    def get_total_price(self):
        return round(self.get_total_articles_price() + self.get_total_services_price(), 2)


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
        return self.reservations.aggregate(quantity=models.Sum('quantity'))['quantity']

    def get_missing_reservation_quantity(self):
        return self.quantity - self.get_reservations_quantity()

    def all_reserved(self):
        return self.get_reservations_quantity() >= self.quantity


class AbstractService(models.Model):
    MAIN_CATEGORIES = (
        ('1', 'Auftragsannahme | Inspektion | Dienstleistung | Diverses'),
        ('2', 'Rahmen'),
        ('3', 'Räder | Bereifung'),
        ('4', 'Tretlager | Pedale | Antrieb'),
        ('5', 'Kettenschaltung | Nabenschaltung'),
        ('6', 'Bremsen'),
        ('7', 'Lichtanlage | Reflektoren'),
        ('8', 'E-Bike Sonderarbeiten'),
    )
    SUB_CATEGORIES = (
        ('1', 'Zubehörmontage'),
        ('2', 'Lenker | Vorbau'),
        ('3', 'Gabel | Lenkkopflager'),
        ('4', 'Gabelfederung'),
        ('5', 'Hinterbaufederung'),
        ('6', 'Sattel | Sattelstütze'),
        ('7', 'Gepäckträger | Rad- und Kettenschützer'),
        ('8', 'Vorderradnabe'),
        ('9', 'Hinterradnabe'),
        ('10', 'Pedale'),
        ('11', 'Kette'),
        ('12', 'Riemen'),
        ('13', 'Hydraulikbremse'),
        ('14', 'Scheibenbremse'),
        ('15', 'Software | Systemkontrolle | Fehler-Diagnose'),
        ('16', 'Instandsetzung'),
    )
    main_category = models.CharField(choices=MAIN_CATEGORIES, max_length=100)
    sub_category = models.CharField(choices=SUB_CATEGORIES, max_length=100, blank=True, null=True)
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

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_work_value_for_type(self, bike_type: str) -> Decimal:
        return getattr(self, bike_type)


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
        return f'{self.stock_article} reserviert für {self.repair_order_article} ({self.quantity})'


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
