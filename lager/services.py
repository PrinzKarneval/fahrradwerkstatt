from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import StockArticle, MovementType, StockMovement, Delivery


class StockService:
    @staticmethod
    @transaction.atomic
    def add_stock(*, stock_article: StockArticle, quantity: int, reference: str):
        stock_article.quantity = F("quantity") + quantity
        stock_article.save(update_fields=["quantity"])
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
    def remove_stock(*, stock_article: StockArticle, quantity: int, reference: str):
        if stock_article.quantity < quantity:
            raise ValidationError("Nicht genug Bestand")

        stock_article.quantity = F("quantity") - quantity
        stock_article.save(update_fields=["quantity"])
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
    def check_in_delivery(delivery: Delivery):
        if delivery.checked_in:
            raise ValidationError("Lieferung wurde bereits eingebucht.")

        for da in delivery.articles.select_for_update():
            if da.checked_in:
                continue

            sa, _ = StockArticle.objects.get_or_create(
                article=da.article,
                price=da.price,
                defaults={"quantity": 0}
            )

            StockService.add_stock(
                stock_article=sa,
                quantity=da.quantity,
                reference=f"Lieferung #{delivery.delivery_number}"
            )

            da.checked_in = timezone.now()
            da.save(update_fields=["checked_in"])

        delivery.checked_in = timezone.now()
        delivery.save(update_fields=['checked_in'])
