from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum, F
from django.urls import reverse
from django.utils import timezone

from lager.services import StockService


def decimal_field_default():
    return models.DecimalField(
        default=Decimal('0.00'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )


class MovementType(models.IntegerChoices):
    IN = 1, 'Zugang'
    OUT = 2, 'Abgang'
    RESERVED = 3, 'Reserviert'
    USED = 4, 'Verwendet'


class Manufacturer(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']
        verbose_name = 'Hersteller'
        verbose_name_plural = 'Hersteller'

    def __str__(self):
        return self.name


class Vendor(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)
    country = models.CharField(max_length=100, default='Deutschland')
    postal = models.CharField(max_length=5)
    city = models.CharField(max_length=50, default='Nürnberg')
    street = models.CharField(max_length=100)
    str_no = models.CharField(max_length=20)

    class Meta:
        verbose_name = 'Händler'
        verbose_name_plural = 'Händler'
        ordering = ['name']

    def __str__(self):
        return self.name


class ArticleType(models.Model):
    parent = models.ForeignKey(
        'self', null=True, blank=True, default=None,
        on_delete=models.PROTECT, related_name='children',
        verbose_name='Übergeordneter Typ'
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']
        verbose_name = 'Artikeltyp'
        verbose_name_plural = 'Artikeltypen'

    def __str__(self):
        return self.name


class AbstractArticle(models.Model):
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.PROTECT, verbose_name='Hersteller')
    type = models.ForeignKey(ArticleType, on_delete=models.CASCADE, verbose_name='Typ')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, verbose_name='Beschreibung')
    ean = models.CharField(max_length=50, unique=True, verbose_name='EAN')
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)], verbose_name='Preis [VK]'
    )

    class Meta:
        abstract = True
        ordering = ['type', 'manufacturer', 'name']

    def __str__(self):
        return f'{self.manufacturer} - {self.name}'


class Article(AbstractArticle):
    minimum = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = 'Artikel'
        verbose_name_plural = 'Artikel'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('article_detail', kwargs={'pk': self.pk})

    def get_stock_quantity(self) -> int:
        return self.stock_articles.aggregate(total=Sum('quantity'))['total'] or 0

    def get_available_quantity(self) -> int:
        return self.get_stock_quantity() - self.get_reserved_quantity() - self.get_requested_quantity()

    def get_reserved_quantity(self) -> int:
        # TODO: Implement real reserved quantity logic
        return 0

    def get_requested_quantity(self) -> int:
        # TODO: Implement real requested quantity logic
        return 0

    def get_ordered_quantity(self):
        return SupplyOrderArticle.objects.filter(
            order__ordered__isnull=False,
            order__deliveries__isnull=True,
            article=self,
        ).aggregate(total=Sum('quantity'))['total'] or 0

    def get_future_quantity(self) -> int:
        return self.get_stock_quantity() + self.get_ordered_quantity()

    def get_avg_price(self):
        agg = StockArticle.objects.filter(article=self).aggregate(
            total_value=Sum(F('price') * F('quantity')),
            total_qty=Sum('quantity')
        )
        if not agg['total_qty']:
            return 0
        return round(agg['total_value'] / agg['total_qty'], 2)


class StockArticleManager(models.Manager):
    def create_with_stock(self, *, article, price, initial_quantity, reference):
        stock_article = self.get_or_create_empty(article=article, price=price)
        StockService.add_stock(stock_article=stock_article, quantity=initial_quantity, reference=reference)
        return stock_article

    def _force_create(self, **kwargs):
        obj = self.model(**kwargs)
        obj._allow_save = True
        obj.save()
        del obj._allow_save
        return obj

    def get_or_create_empty(self, *, article, price):
        return self.get(article=article, price=price) \
            if self.filter(article=article, price=price)\
            else self._force_create(article=article, price=price)


class StockArticle(models.Model):
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='stock_articles', verbose_name='Lagerartikel')
    quantity = models.PositiveSmallIntegerField(default=0)
    price = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])

    objects = StockArticleManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['article', 'price'], name='unique_article_price')]
        ordering = ['article']
        verbose_name = 'Lagerartikel'
        verbose_name_plural = 'Lagerartikel'

    def __str__(self):
        return self.article.name

    def clean(self):
        if self.quantity < 0:
            raise ValidationError('Bestand darf nicht negativ sein.')

    def save(self, *args, **kwargs):
        if not getattr(self, '_allow_save', False):
            raise ValidationError(
                "StockArticle darf nicht direkt gespeichert werden. "
                "Nutze StockService oder den Manager."
            )
        super().save(*args, **kwargs)


class StockMovement(models.Model):
    stock_article = models.ForeignKey(StockArticle, on_delete=models.PROTECT, related_name='movements')
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=7, decimal_places=2, verbose_name='Preis')
    movement_type = models.PositiveSmallIntegerField(choices=MovementType.choices)
    reference = models.CharField(max_length=100)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created']
        verbose_name = 'Lagerbewegung'
        verbose_name_plural = 'Lagerbewegungen'


class SupplyOrder(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, verbose_name='Händler')
    order_number = models.CharField(max_length=100, blank=True, verbose_name='Bestellnummer')
    created = models.DateTimeField(auto_now_add=True, verbose_name='Erstellt')
    ordered = models.DateTimeField(blank=True, null=True, verbose_name='Bestellt')

    class Meta:
        ordering = ['-created']
        verbose_name = 'Bestellung'
        verbose_name_plural = 'Bestellungen'

    def __str__(self):
        return f'#{self.pk} {self.vendor}'

    def submit(self):
        if not self.ordered:
            self.ordered = timezone.now()
            self.save(update_fields=['ordered'])

    def get_absolute_url(self):
        return reverse('supply_order_detail', kwargs={'pk': self.pk})

    def get_article_count(self):
        return self.positions.aggregate(total=Sum('quantity'))['total'] or 0

    def get_total_value(self):
        return round(self.positions.aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0, 2)


class SupplyOrderArticle(models.Model):
    order = models.ForeignKey(SupplyOrder, on_delete=models.CASCADE, related_name='positions', verbose_name='Bestellung')
    article = models.ForeignKey(Article, on_delete=models.PROTECT, verbose_name='Artikel')
    quantity = models.PositiveIntegerField(verbose_name='Menge')
    price = models.DecimalField(max_digits=7, decimal_places=2, verbose_name='Preis [EK]')

    def __str__(self):
        return f'{self.order} - {self.article}'

    def get_total_value(self):
        return self.quantity * self.price


class Delivery(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    order = models.ForeignKey(SupplyOrder, on_delete=models.CASCADE, related_name='deliveries', blank=True, null=True)
    delivery_number = models.CharField(max_length=100)
    delivery_date = models.DateField()
    checked_in = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-delivery_date']
        verbose_name = 'Lieferung'
        verbose_name_plural = 'Lieferungen'

    def __str__(self):
        return f'{self.delivery_number} {self.vendor}'

    def get_absolute_url(self):
        return reverse("delivery_detail", kwargs={"pk": self.pk})

    def get_article_count(self):
        return self.articles.aggregate(total=Sum('quantity'))['total'] or 0

    def get_total_value(self):
        return round(self.articles.aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0, 2)


class DeliveryArticle(models.Model):
    delivery = models.ForeignKey(Delivery, on_delete=models.PROTECT, related_name='articles', verbose_name='Lieferung')
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='deliveries', verbose_name='Lieferartikel')
    quantity = models.PositiveIntegerField(verbose_name='Menge')
    price = models.DecimalField(max_digits=7, decimal_places=2, verbose_name='Preis [EK]')
    checked_in = models.DateTimeField(blank=True, null=True, verbose_name='Eingelagert')

    class Meta:
        verbose_name = 'Lieferartikel'
        verbose_name_plural = 'Lieferartikel'

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.pk:
            old = DeliveryArticle.objects.get(pk=self.pk)
            if old.checked_in:
                raise ValidationError('Cannot modify a finalized receipt!')
        super().save(*args, **kwargs)

    def get_total_value(self):
        return round(self.quantity * self.price, 2)


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
        return getattr(self, bike_type, Decimal('0.00'))


class Service(AbstractService):
    class Meta:
        verbose_name = 'Service'
        verbose_name_plural = 'Services'
