from lager.models import *


continental = Manufacturer.objects.create(name="Continental")
maxxis = Manufacturer.objects.create(name="Maxxis")
dt_swiss = Manufacturer.objects.create(name="DT Swiss")
hartje = Vendor.objects.create(
    name="Hartje",
    email="",
    phone="",
    postal="12345",
    city="AS",
    street="kasdjf",
    str_no="sdlkgfj"
)
reifen = ArticleType.objects.create(name="Reifen")
felgen = ArticleType.objects.create(name="Felgen")
kryp_re_ds = Article.objects.create(
    manufacturer=continental,
    type=reifen,
    name="Kryptotal-Re Downhill Soft 29x2.40",
    ean="4019238080773",
    price=Decimal("93.95"))
kryp_re_dss = Article.objects.create(
    manufacturer=continental,
    type=reifen,
    name="Kryptotal-Re Downhill Super Soft 29x2.40",
    ean="4019238063196",
    price=Decimal("93.95"))
aggressor = Article.objects.create(
    manufacturer=maxxis,
    type=reifen,
    name="Aggressor EN/DH DD TR 29x2.30 ",
    ean="1177",
    price=Decimal("74.90"))
highroller = Article.objects.create(
    manufacturer=maxxis,
    type=reifen,
    name="Highroller 2 TR/AM EXO TR 3C MaxxTerra 29x2.30 ",
    ean="1079",
    price=Decimal("74.90"))
ex511 = Article.objects.create(
    manufacturer=dt_swiss,
    type=felgen,
    name="EX 511 29 39 MM DB VI",
    ean="RDEX51CDPW32SA6298",
    price=Decimal("99.00"))
so = SupplyOrder.objects.create(vendor=hartje)
soa1 = SupplyOrderArticle.objects.create(order=so, article=kryp_re_ds, quantity=6, price=Decimal("29.90"))
soa2 = SupplyOrderArticle.objects.create(order=so, article=kryp_re_dss, quantity=6, price=Decimal("33.90"))
soa3 = SupplyOrderArticle.objects.create(order=so, article=aggressor, quantity=4, price=Decimal("35.99"))
soa4 = SupplyOrderArticle.objects.create(order=so, article=highroller, quantity=4, price=Decimal("35.99"))
soa5 = SupplyOrderArticle.objects.create(order=so, article=ex511, quantity=2, price=Decimal("60.00"))
so.submit()
delivery = Delivery.objects.create(vendor=hartje, order=so, delivery_number="20809823", delivery_date=timezone.now().date())
da1 = DeliveryArticle.objects.create(delivery=delivery, article=kryp_re_ds, quantity=6, price=Decimal("29.90"))
da2 = DeliveryArticle.objects.create(delivery=delivery, article=kryp_re_dss, quantity=6, price=Decimal("33.90"))
da3 = DeliveryArticle.objects.create(delivery=delivery, article=aggressor, quantity=4, price=Decimal("35.99"))
da4 = DeliveryArticle.objects.create(delivery=delivery, article=highroller, quantity=4, price=Decimal("35.99"))
da5 = DeliveryArticle.objects.create(delivery=delivery, article=ex511, quantity=2, price=Decimal("60.00"))

delivery.check_in()

