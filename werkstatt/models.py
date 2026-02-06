from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum, PositiveSmallIntegerField
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone


BIKE_TYPES = (('children_bike', 'Children\'s bike'),
              ('hub_gear', 'Hub Gear'),
              ('derailleur', 'Derailleur'),
              ('mtb', 'MTB'),
              ('road_bike', 'Road Bike'))

RESERVATION_RESERVED = 1
RESERVATION_INSTALLED = 2
RESERVATION_CANCELLED = 3

def decimal_field_default():
    return models.DecimalField(default=Decimal("0.00"), max_digits=7, decimal_places=2,
                               validators=[MinValueValidator(0)])

class Label(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return self.name


class Manufacturer(Label):
    pass


class ArticleType(models.Model):
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children',
                               default=None)
    name = models.CharField(max_length=20)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AbstractArticle(models.Model):
    manufacturer = models.ForeignKey(Manufacturer, models.CASCADE)
    type = models.ForeignKey(ArticleType, models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ean = models.CharField(max_length=13)
    price = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)], null=True,
                                blank=True)

    class Meta:
        abstract = True
        ordering = ["type", "manufacturer", "name"]

    def __str__(self):
        return f"{self.type} {self.manufacturer} {self.name}"


class Article(AbstractArticle):
    pass


class AbstractService(models.Model):
    MAIN_CATEGORIES = (
        ("1", "Auftragsannahme | Inspektion | Dienstleistung | Diverses"),
        ("2", "Rahmen"),
        ("3", "Räder | Bereifung"),
        ("4", "Tretlager | Pedale | Antrieb"),
        ("5", "Kettenschaltung | Nabenschaltung"),
        ("6", "Bremsen"),
        ("7", "Lichtanlage | Reflektoren"),
        ("8", "E-Bike Sonderarbeiten"),
    )
    SUB_CATEGORIES = (
        ("1", "Zubehörmontage"),
        ("2", "Lenker | Vorbau "),
        ("3", "Gabel | Lenkkopflager"),
        ("4", "Gabelfederung"),
        ("5", "Hinterbaufederung"),
        ("6", "Sattel |Sattelstütze"),
        ("7", "Gepäckträger |Rad- und Kettenschützer"),
        ("8", "Vorderradnabe"),
        ("9", "Hinterradnabe"),
        ("10", "Pedale"),
        ("11", "Kette"),
        ("12", "Riemen"),
        ("13", "Hydraulikbremse"),
        ("14", "Scheibenbremse"),
        ("15", "Software |Systemkontrolle | Fehler-Diagnose"),
        ("16", "Instandsetzung"),
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
        return getattr(self, bike_type, Decimal("0.00"))


class Service(AbstractService):
    pass


class StockArticle(models.Model):
    article = models.ForeignKey(Article, models.PROTECT)
    minimum = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0)])
    quantity = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0)])

    def __str__(self):
        return f"{self.quantity} {self.article}"

    def get_requested_quantity(self):
        return self.requests.all().aggregate(Sum('quantity'))['quantity__sum'] or 0

    def get_reserved_quantity(self):
        return (self.reservations.filter(status=RESERVATION_RESERVED)
                .aggregate(models.Sum('quantity'))['quantity__sum'] or 0)

    def get_available_quantity(self):
        return self.quantity - self.get_reserved_quantity()

    def get_ordered_quantity(self):
        return (
                SupplyOrderArticle.objects.filter(
                    article=self.article,
                    order__delivered__isnull=True
                ).aggregate(models.Sum('quantity'))['quantity__sum'] or 0
        )

    def get_future_quantity(self):
        return self.quantity + self.get_ordered_quantity() - self.get_reserved_quantity()


class StockArticleRequest(models.Model):
    repair_order_article = models.ForeignKey("RepairOrderArticle", models.CASCADE)
    stock_article = models.ForeignKey(StockArticle, models.CASCADE, related_name='requests')
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    quantity_ordered = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0)])
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repair_order_article", "stock_article"],
                name="unique_request_per_roa"
            )
        ]

    def __str__(self):
        return f"{self.stock_article} {self.quantity}"


class StockArticleReservation(models.Model):
    STATUS = (
        (RESERVATION_RESERVED, 'Reserved'),
        (RESERVATION_INSTALLED, 'Installed'),
        (RESERVATION_CANCELLED, 'Cancelled'),
    )
    repair_order_article = models.ForeignKey("RepairOrderArticle", on_delete=models.CASCADE,
                                             related_name="reservations")
    stock_article = models.ForeignKey(StockArticle, on_delete=models.PROTECT, related_name="reservations")
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    status = models.PositiveSmallIntegerField(choices=STATUS, default=RESERVATION_RESERVED)

    def complete(self):
        if self.stock_article.quantity < self.quantity:
            raise ValueError("Stock article quantity must be greater than stock article quantity")

        self.stock_article.quantity -= self.quantity
        self.stock_article.save()
        self.status = RESERVATION_INSTALLED
        self.save()

    def cancel(self):
        self.status = RESERVATION_CANCELLED
        self.save(update_fields=["status"])

    def clean(self):
        # Stelle sicher, dass der Artikel identisch ist
        if self.repair_order_article.stock_article != self.stock_article:
            raise ValidationError(
                "Artikel in RepairOrderArticle und StockArticle müssen identisch sein."
            )

    def save(self, *args, **kwargs):
        self.full_clean()  # ruft clean() auf, bevor gespeichert wird
        super().save(*args, **kwargs)


class SupplyOrder(models.Model):
    DRAFT = 1
    SUBMITTED = 2
    RECEIVED = 3
    CANCELLED = 9

    STATUS = (
        (DRAFT, 'Draft'),
        (SUBMITTED, 'Submitted'),
        (RECEIVED, 'Received'),
        (CANCELLED, 'Cancelled'),
    )

    status = models.PositiveSmallIntegerField(choices=STATUS, default=DRAFT)
    submitted = models.DateField(blank=True, null=True)
    delivered = models.DateField(blank=True, null=True)
    created = models.DateTimeField(editable=False)
    modified = models.DateTimeField()

    def __str__(self) -> str:
        return f"Supply Order [{self.pk}]"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.created = timezone.now()
        self.modified = timezone.now()
        return super().save(*args, **kwargs)

    def submit_order(self) -> None:
        self.submitted = timezone.now()
        self.status = SupplyOrder.SUBMITTED
        self.save()

    @transaction.atomic
    def receive(self) -> None:
        if self.status == self.RECEIVED:
            return

        now = timezone.now().date()

        for pos in self.articles.all():
            stock, _ = StockArticle.objects.select_for_update().get_or_create(
                article=pos.article,
                defaults={"quantity": 0}
            )
            stock.quantity += pos.quantity
            stock.save()

        self.delivered = now
        self.status = self.RECEIVED
        self.save()


class SupplyOrderArticle(models.Model):
    order = models.ForeignKey(SupplyOrder, models.CASCADE, related_name='articles')
    article = models.ForeignKey(Article, models.PROTECT)
    quantity = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0)])


class SupplyOrderArticleReceived(models.Model):
    soa = models.ForeignKey(SupplyOrder, models.CASCADE, related_name='received_articles')
    delivered = models.DateField(blank=True, null=True)
    quantity = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0)])


class Address(models.Model):
    postal = models.CharField(max_length=5)
    city = models.CharField(max_length=50, default="Nürnberg")
    street = models.CharField(max_length=100)
    str_no = models.CharField(max_length=5)

    class Meta:
        abstract = True


class Customer(Address):
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("customer_detail", kwargs={"pk": self.pk})


class Vendor(Address):
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)
    country = models.CharField(max_length=100, default='Deutschland')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class RepairOrder(models.Model):
    date_created = models.DateField(auto_now_add=True)
    date_finished = models.DateField(blank=True, null=True)
    customer = models.ForeignKey(Customer, models.PROTECT)
    description = models.TextField()
    bike_type = models.CharField(choices=BIKE_TYPES, default="derailleur", max_length=20)
    bike_model = models.CharField(max_length=200)
    color = models.CharField(max_length=20)
    serial_number = models.CharField(max_length=30)
    is_cargo_bike = models.BooleanField(default=False)
    has_hub_engine = models.BooleanField(default=False)
    has_mid_engine = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date_finished', 'date_created']

    def __str__(self) -> str:
        return f'{self.pk} | {self.customer}'

    def get_absolute_url(self) -> str:
        return reverse("repair_order_detail", kwargs={"pk": self.pk})

    def get_total_article_price(self) -> Decimal:
        total = Decimal(0.0)
        for a in self.articles.all():
            total += a.get_total()
        return total


class RepairOrderArticle(models.Model):
    order = models.ForeignKey(RepairOrder, models.CASCADE, related_name='articles')
    stock_article = models.ForeignKey(StockArticle, models.CASCADE)
    quantity = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0)])
    installed = models.BooleanField(default=False)

    def __str__(self) -> str:
        return str(self.stock_article)

    def get_total(self) -> Decimal:
        return self.quantity * self.stock_article.article.price

    def get_reserved_quantity(self) -> int:
        return self.reservations.filter(status=RESERVATION_RESERVED).aggregate(total=Sum('quantity'))['total'] or 0

    def get_requested_quantity(self) -> int:
        return StockArticleRequest.objects.filter(stock_article=self.stock_article, repair_order_article=self
            ).aggregate(total=Sum('quantity'))['total'] or 0

    def all_parts_available(self) -> bool:
        return self.quantity <= self.get_reserved_quantity()


class RepairOrderService(models.Model):
    PLANNED = 1
    DONE = 2

    STATUS = (
        (PLANNED, 'Planned'),
        (DONE, 'Done'),
    )

    order = models.ForeignKey(RepairOrder, models.CASCADE, related_name='services')
    service = models.ForeignKey(Service, models.CASCADE)
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    status = PositiveSmallIntegerField(choices=STATUS, default=PLANNED)

    def __str__(self):
        return str(self.service)

    def get_work_value(self):
        bike_type = self.order.bike_type
        wv = self.service.get_work_value_for_type(bike_type)
        if self.order.is_cargo_bike:
            wv += self.service.get_work_value_for_type("cargo_bike")
        if self.order.has_hub_engine:
            wv += self.service.get_work_value_for_type("hub_engine")
        if self.order.has_mid_engine:
            wv += self.service.get_work_value_for_type("mid_engine")
        return wv


class WorkRate(models.Model):
    start = models.DateField(default=timezone.now, unique=True)
    rate = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ['-start']

    def __str__(self) -> str:
        return str(self.rate)

    @staticmethod
    def get_current_rate() -> Decimal:
        today = timezone.now().date()
        item = (
            WorkRate.objects
            .filter(start__lte=today)
            .order_by('-start')
            .first()
        )
        if not item:
            raise ValidationError("Kein gültiger Stundensatz definiert")

        return Decimal(item.rate)


class Invoice(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    date_paid = models.DateField()
    customer = models.ForeignKey(Customer, models.PROTECT)
    postal = models.CharField(max_length=5)
    city = models.CharField(max_length=50, default="Nürnberg")
    street = models.CharField(max_length=100)
    str_no = models.CharField(max_length=5)
    description = models.TextField()
    bike_type = models.CharField(choices=BIKE_TYPES, default="derailleur", max_length=20)
    bike_model = models.CharField(max_length=200)
    color = models.CharField(max_length=20)
    serial_number = models.CharField(max_length=50)

    def __str__(self) -> str:
        return f"Invoice [{self.pk}]"

    def get_total_articles(self) -> float:
        articles = self.invoicearticle_set.all()
        return sum(map(lambda a: a.get_total(), articles))

    def get_total_services(self) -> float:
        services = self.invoiceservice_set.all()
        return sum(map(lambda s: s.get_total(), services))

    def get_total(self) -> Decimal:
        return (
                Decimal(self.get_total_articles()) +
                Decimal(self.get_total_services())
        )


class InvoiceArticle(AbstractArticle):
    invoice = models.ForeignKey(Invoice, models.PROTECT)
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=7, decimal_places=2)

    def get_total(self) -> Decimal:
        return self.quantity * self.price


class InvoiceService(AbstractService):
    invoice = models.ForeignKey(Invoice, models.PROTECT)
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=7, decimal_places=2)

    def get_total(self) -> Decimal:
        return self.quantity * self.price
