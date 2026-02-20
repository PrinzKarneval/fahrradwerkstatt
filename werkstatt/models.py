from django.db.models import DecimalField, Subquery, OuterRef

from lager.models import *


class Customer(models.Model):
    name = models.CharField(max_length=100, verbose_name='Name')
    email = models.EmailField(blank=True, null=True, verbose_name='Email')
    phone = models.CharField(max_length=25, blank=True, null=True, verbose_name='Telefon')
    postal = models.CharField(max_length=5, verbose_name='PLZ')
    city = models.CharField(max_length=50, default='Erlangen', verbose_name='Ort')
    street = models.CharField(max_length=100, verbose_name='Straße')
    str_no = models.CharField(max_length=20, verbose_name='Nr.')

    class Meta:
        ordering = ['name']
        verbose_name = 'Kunde'
        verbose_name_plural = 'Kunden'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('customer_detail', kwargs={'pk': self.pk})

    def get_open_orders(self):
        return self.orders.filter(date_finished__isnull=True).count()


class RepairOrderQuerySet(models.QuerySet):

    def with_totals(self):
        """
        Annotates:
            total_articles
            total_services
            total_price
        All calculated in ONE database query.
        """

        # --- Article Subquery ---
        article_subquery = RepairOrderArticle.objects.filter(order=OuterRef("pk")).annotate(
            total=F("stock_article__article__price") * F("quantity")
        ).values("order").annotate(sum_total=Sum("total")).values("sum_total")

        # --- Service Subquery ---
        service_subquery = RepairOrderService.objects.filter(order=OuterRef("pk")).annotate(
            price=Case(
                When(order__is_ebike=True, then=F("service__ebike_price")),
                default=F("service__normal_price"),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            total=F("price") * F("quantity"),
        ).values("order").annotate(sum_total=Sum("total")).values("sum_total")

        return self.annotate(
            total_articles=Coalesce(
                Subquery(
                    article_subquery,
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                ),
                Value(0),
            ),
            total_services=Coalesce(
                Subquery(
                    service_subquery,
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                ),
                Value(0),
            ),
        ).annotate(
            total_price=F("total_articles") + F("total_services")
        )


class RepairOrderManager(models.Manager):
    def get_queryset(self):
        return RepairOrderQuerySet(self.model, using=self._db)

    def with_totals(self):
        return self.get_queryset().with_totals()


class RepairOrder(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders', verbose_name='Kunde')
    date_created = models.DateTimeField(auto_now_add=True, verbose_name='Erstellt')
    date_finished = models.DateTimeField(blank=True, null=True, verbose_name='Abgeschlossen')
    description = models.TextField(blank=True, verbose_name='Beschreibung')
    is_ebike = models.BooleanField(default=False, verbose_name='Ist E-Bike')
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Hersteller')
    bike_model = models.CharField(max_length=50, blank=True, null=True, verbose_name='Modell')
    color = models.CharField(max_length=30, blank=True, null=True, verbose_name='Farbe')
    serial_number = models.CharField(max_length=50, blank=True, null=True, verbose_name='Seriennummer')

    objects = RepairOrderManager()

    class Meta:
        ordering = ['-date_created']
        verbose_name = 'Reparaturauftrag'
        verbose_name_plural = 'Reparaturaufträge'

    def __str__(self):
        return f'RO #{self.pk} - {self.customer}'

    def get_absolute_url(self):
        return reverse('repair_order_detail', kwargs={'pk': self.pk})

    def get_total_articles_price(self):
        return self.articles.aggregate(
            total=Coalesce(
                Sum(
                    F('stock_article__article__price') * F('quantity'),
                    output_field=DecimalField(decimal_places=2, max_digits=10),
                ), 0
            )
        )['total']

    def get_total_services_price(self):
        price_field = (
            'service__ebike_price'
            if self.is_ebike
            else 'service__normal_price'
        )
        return self.services.aggregate(
            total=Coalesce(
                Sum(
                    F(price_field) * F('quantity'),
                    output_field=DecimalField(decimal_places=2, max_digits=10),
                ), 0
            )
        )['total']

    def get_total_price(self) -> Decimal:
        return (self.get_total_articles_price() + self.get_total_services_price()).quantize(Decimal('0.01'))


class RepairOrderArticle(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name='articles',
                              verbose_name='Reparaturauftrag')
    stock_article = models.ForeignKey(StockArticle, on_delete=models.PROTECT, verbose_name='Lagerartikel')
    quantity = models.PositiveIntegerField(default=1, verbose_name='Anzahl')

    class Meta:
        constraints = [
            UniqueConstraint(fields=['order', 'stock_article'], name='unique_order_stock_article')
        ]
        ordering = ['order', 'stock_article']
        verbose_name = 'Artikel im Reparaturauftrag'
        verbose_name_plural = 'Artikel im Reparaturauftrag'

    def __str__(self):
        return f'{self.stock_article} x {self.quantity}'

    def get_total(self) -> Decimal:
        return self.stock_article.price * self.quantity

    def get_reservations_quantity(self):
        return self.reservations.aggregate(quantity=Coalesce(Sum('quantity'), 0))['quantity']

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
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name='services',
                                 verbose_name='Kategorie')
    number = models.PositiveSmallIntegerField(verbose_name='Nummer')
    name = models.CharField(max_length=100)
    normal_price = models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Normalpreis')
    ebike_price = models.DecimalField(decimal_places=2, max_digits=10, verbose_name='E-Bike-Preis')

    class Meta:
        abstract = True
        ordering = ['category', 'name']
        verbose_name = 'Service'
        verbose_name_plural = 'Services'

    def __str__(self):
        return self.name


class Service(AbstractService):
    pass


class RepairOrderService(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name='services',
                              verbose_name='Reparaturauftrag')
    service = models.ForeignKey(Service, on_delete=models.PROTECT, verbose_name='Service')
    quantity = models.PositiveIntegerField(default=1, verbose_name='Anzahl')

    class Meta:
        constraints = [
            UniqueConstraint(fields=['order', 'service'], name='unique_order_service')
        ]
        ordering = ['order', 'service']
        verbose_name = 'Service im Reparaturauftrag'
        verbose_name_plural = 'Services im Reparaturauftrag'

    def __str__(self):
        return f'{self.service.name} x {self.quantity}'

    def get_price(self) -> Decimal:
        if self.order.is_ebike:
            return self.service.ebike_price * self.quantity
        return self.service.normal_price * self.quantity


class StockArticleReservation(models.Model):
    repair_order_article = models.ForeignKey(RepairOrderArticle, on_delete=models.CASCADE, related_name='reservations',
                                             verbose_name='Reparaturauftrag')
    stock_article = models.ForeignKey(StockArticle, on_delete=models.CASCADE, related_name='reservations',
                                      verbose_name='Lagerartikel')
    quantity = models.PositiveIntegerField(default=0, verbose_name='Anzahl')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['repair_order_article', 'stock_article'], name='unique_roa_and_sa'),
        ]
        ordering = ['repair_order_article', 'stock_article']
        verbose_name = 'Reservierter Lagerartikel'
        verbose_name_plural = 'Reservierte Lagerartikel'

    def __str__(self):
        return f'{self.stock_article} reserviert für {self.repair_order_article} ({self.quantity})'


class ArticleRequest(models.Model):
    repair_order_article = models.ForeignKey(RepairOrderArticle, on_delete=models.CASCADE, related_name='requests',
                                             verbose_name='Reparaturauftrag')
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='requests', verbose_name='Artikel')
    quantity = models.PositiveIntegerField(default=0, verbose_name='Anzahl')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['repair_order_article', 'article'], name='unique_roa_and_article'),
        ]
        ordering = ['repair_order_article', 'article']
        verbose_name = 'Angeforderter Lagerartikel'
        verbose_name_plural = 'Angeforderte Lagerartikel'

    def __str__(self):
        return f'{self.article} angefordert für {self.repair_order_article} ({self.quantity})'


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
    category = models.CharField(max_length=100)
    number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    price = decimal_field_default()
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Rechnungsservice'
        verbose_name_plural = 'Rechnungsservices'

    def total(self) -> Decimal:
        return self.price * self.quantity
