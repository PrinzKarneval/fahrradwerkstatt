from decimal import Decimal
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum, F, Q, UniqueConstraint, Case, When, IntegerField, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

ZERO_DECIMAL = Decimal('0.00')


def decimal_field_default():
    return models.DecimalField(
        default=Decimal('0.00'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )


class MovementType(models.IntegerChoices):
    IN_DELIVERY = 1, 'IN | LIEFERUNG'
    OUT_CORRECTION = 2, 'OUT | LIEFERKORREKTUR'
    OUT_RETURN = 3, 'OUT | LIEFER-RETOUR'
    OUT_SOLD = 6, 'OUT | VERKAUFT'
    IN_STORNO = 7, 'IN | RECHNUNG STORNIERT'
    OUT_SCRAP = 8, 'OUT | AUSSCHUSS'


STOCK_IN = [MovementType.IN_DELIVERY, MovementType.IN_STORNO]
STOCK_OUT = [MovementType.OUT_CORRECTION, MovementType.OUT_RETURN, MovementType.OUT_SOLD, MovementType.OUT_SCRAP]


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
        ordering = ['name']
        verbose_name = 'Händler'
        verbose_name_plural = 'Händler'

    def __str__(self):
        return self.name


class ArticleType(models.Model):
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children',
                               verbose_name='Übergeordneter Typ')
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

    def get_stock_quantity(self):
        agg = StockMovement.objects.filter(stock_article__article=self).aggregate(
            total_in=Coalesce(Sum('quantity', filter=Q(movement_type__in=STOCK_IN)), 0),
            total_out=Coalesce(Sum('quantity', filter=Q(movement_type__in=STOCK_OUT)), 0)
        )
        return agg['total_in'] - agg['total_out']

    def get_reserved_quantity(self):
        from werkstatt.models import StockArticleReservation
        return StockArticleReservation.objects.filter(stock_article__article=self) \
            .aggregate(total=Coalesce(Sum('quantity'), 0))['total']

    def get_requested_quantity(self):
        from werkstatt.models import ArticleRequest
        return ArticleRequest.objects.filter(article=self) \
            .aggregate(total=Coalesce(Sum('quantity'), 0))['total']

    def get_available_quantity(self):
        return max(0, self.get_stock_quantity() - self.get_reserved_quantity() - self.get_requested_quantity())

    def get_ordered_quantity(self):
        return SupplyOrderArticle.objects.filter(
            article=self,
            order__ordered__isnull=False,
            order__deliveries__isnull=True
        ).aggregate(total=Coalesce(Sum('quantity'), 0))['total']

    def get_future_quantity(self):
        return self.get_available_quantity() + self.get_ordered_quantity()

    def get_avg_price(self):
        stock_articles = (
            self.stock_articles
            .annotate(
                total_in=Coalesce(
                    Sum('movements__quantity',
                        filter=Q(movements__movement_type__in=STOCK_IN)), 0
                ),
                total_out=Coalesce(
                    Sum('movements__quantity',
                        filter=Q(movements__movement_type__in=STOCK_OUT)), 0
                ),
            )
            .annotate(qty=F('total_in') - F('total_out'))
        )

        total_qty = 0
        total_value = Decimal("0.00")

        for sa in stock_articles:
            total_qty += sa.qty
            total_value += Decimal(sa.qty) * sa.price

        if total_qty == 0:
            return ZERO_DECIMAL

        return (total_value / Decimal(total_qty)).quantize(Decimal("0.01"))


def quantity_expression_for_article():
    return Coalesce(
        Sum(
            Case(
                When(movements__movement_type__in=STOCK_IN,
                     then=F('movements__quantity')),
                When(movements__movement_type__in=STOCK_OUT,
                     then=-F('movements__quantity')),
                default=Value(0),
                output_field=IntegerField(),
            )
        ),
        Value(0)
    )


def quantity_expression_for_movement():
    return Coalesce(
        Sum(
            Case(
                When(movement_type__in=STOCK_IN, then=F('quantity')),
                When(movement_type__in=STOCK_OUT, then=-F('quantity')),
                default=Value(0),
                output_field=IntegerField(),
            )
        ),
        Value(0)
    )


class StockArticleManager(models.Manager):
    def with_quantity(self):
        return self.get_queryset().annotate(
            _quantity=quantity_expression_for_article()
        )


class StockArticle(models.Model):
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='stock_articles',
                                verbose_name='Lagerartikel')
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    objects = StockArticleManager()

    class Meta:
        constraints = [UniqueConstraint(fields=["article", "price"], name='unique_stock_article_price')]
        ordering = ['article']
        verbose_name = 'Lagerartikel'
        verbose_name_plural = 'Lagerartikel'

    def __str__(self):
        return self.article.name

    @property
    def quantity(self):
        if hasattr(self, "_quantity"):
            return self._quantity

        return self.movements.aggregate(
            quantity=quantity_expression_for_movement()
        )["quantity"]

    def get_reserved_quantity(self):
        return self.reservations.aggregate(total=Coalesce(Sum('quantity'), 0))['total']

    def get_available_quantity(self):
        return self.quantity - self.get_reserved_quantity()

    def get_requested_quantity(self):
        return self.requests.aggregate(total=Coalesce(Sum('quantity'), 0))['total']

    def get_ordered_quantity(self):
        return SupplyOrderArticle.objects.filter(
            article=self.article,
            price=self.price,
            order__ordered__isnull=False,
            order__deliveries__isnull=True
        ).aggregate(total=Coalesce(Sum('quantity'), 0))['total']

    def get_future_quantity(self):
        stock = self.get_quantity()
        reserved = self.get_reserved_quantity()
        requested = self.get_requested_quantity()
        ordered = self.get_ordered_quantity()
        return stock - reserved - requested + ordered


class ImmutableQuerySet(models.QuerySet):
    def update(self, *args, **kwargs):
        raise PermissionDenied("Bulk-Update ist für StockMovement nicht erlaubt.")

    def bulk_update(self, *args, **kwargs):
        raise PermissionDenied("bulk_update ist für StockMovement nicht erlaubt.")

    def delete(self):
        raise PermissionDenied("Bulk-Delete ist für StockMovement nicht erlaubt.")


class ImmutableManager(models.Manager):
    def get_queryset(self):
        return ImmutableQuerySet(self.model, using=self._db)


class ImmutableModel(models.Model):
    objects = ImmutableManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied(
                f"{self.__class__.__name__} darf nicht verändert werden."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(
            f"{self.__class__.__name__} darf nicht gelöscht werden."
        )


class StockMovement(ImmutableModel):
    stock_article = models.ForeignKey(StockArticle, on_delete=models.PROTECT, related_name='movements')
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Preis')
    movement_type = models.PositiveSmallIntegerField(choices=MovementType.choices)
    reference = models.CharField(max_length=100)
    created = models.DateTimeField(auto_now_add=True)

    objects = ImmutableManager()

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
    order = models.ForeignKey(SupplyOrder, on_delete=models.CASCADE, related_name='positions',
                              verbose_name='Bestellung')
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
    is_correction = models.BooleanField(default=False)
    checked_in = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-delivery_date']
        verbose_name = 'Lieferung'
        verbose_name_plural = 'Lieferungen'

    def __str__(self):
        return f'{self.delivery_number} {self.vendor}'

    def get_absolute_url(self):
        return reverse('delivery_detail', kwargs={'pk': self.pk})

    def get_article_count(self):
        return self.articles.aggregate(total=Sum('quantity'))['total'] or 0

    def get_total_value(self):
        return round(self.articles.aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0, 2)


class DeliveryArticle(models.Model):
    delivery = models.ForeignKey(Delivery, on_delete=models.PROTECT, related_name='articles', verbose_name='Lieferung')
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='deliveries',
                                verbose_name='Lieferartikel')
    quantity = models.PositiveIntegerField(verbose_name='Menge', validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=7, decimal_places=2, verbose_name='Preis [EK]')

    class Meta:
        verbose_name = 'Lieferartikel'
        verbose_name_plural = 'Lieferartikel'

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.pk:
            delivery = Delivery.objects.get(pk=self.delivery.pk)
            if delivery.checked_in:
                raise ValidationError('Cannot modify a finalized receipt!')
        super().save(*args, **kwargs)

    def get_total_value(self):
        return round(self.quantity * self.price, 2)
