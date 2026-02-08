from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone


class StockService:
    @staticmethod
    @transaction.atomic
    def add_stock(*, stock_article, quantity: int, reference: str):
        from .models import StockMovement, MovementType

        if quantity <= 0:
            raise ValidationError("Menge muss größer als 0 sein.")

        stock_article._allow_save = True
        stock_article.quantity = F("quantity") + quantity
        stock_article.save(update_fields=["quantity"])
        del stock_article._allow_save
        stock_article.refresh_from_db()

        StockMovement.objects.create(
            stock_article=stock_article,
            quantity=quantity,
            price=stock_article.price,
            movement_type=MovementType.IN,
            reference=reference,
        )

    @staticmethod
    @transaction.atomic
    def remove_stock(*, stock_article, quantity: int, reference: str):
        from .models import StockMovement, MovementType

        if quantity <= 0:
            raise ValidationError("Menge muss größer als 0 sein.")

        stock_article.refresh_from_db()
        if stock_article.quantity < quantity:
            raise ValidationError("Nicht genug Bestand verfügbar.")

        stock_article._allow_save = True
        stock_article.quantity = F("quantity") - quantity
        stock_article.save(update_fields=["quantity"])
        del stock_article._allow_save
        stock_article.refresh_from_db()

        StockMovement.objects.create(
            stock_article=stock_article,
            quantity=quantity,
            price=stock_article.price,
            movement_type=MovementType.OUT,
            reference=reference,
        )


class DeliveryService:
    @staticmethod
    @transaction.atomic
    def check_in_delivery(delivery):
        from .models import StockArticle

        if delivery.checked_in:
            raise ValidationError("Lieferung wurde bereits eingebucht.")

        delivery_articles = delivery.articles.select_for_update().select_related("article")
        for da in delivery_articles:
            if da.checked_in:
                continue

            # zuerst StockArticle über Manager holen/erstellen
            sa = StockArticle.objects.get_or_create_empty(article=da.article, price=da.price)
            # dann sperren für parallele Buchungen
            sa = StockArticle.objects.select_for_update().get(pk=sa.pk)

            StockService.add_stock(
                stock_article=sa,
                quantity=da.quantity,
                reference=f"Lieferung {delivery.delivery_number}"
            )

            da.checked_in = timezone.now()
            da.save(update_fields=["checked_in"])

        delivery.checked_in = timezone.now()
        delivery.save(update_fields=["checked_in"])


class DemandService:
    @staticmethod
    @transaction.atomic
    def update_demands():
        # Platzhalter für zukünftige Logik
        pass
