from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from lager.models import StockArticle, StockMovement, MovementType


class StockService:
    """
    Ledger-based stock management service.
    Tracks all stock changes via StockMovement:
    - IN: new stock
    - OUT: removal
    - RESERVED: reserved for orders
    - USED: consumed/reserved used
    """

    @staticmethod
    @transaction.atomic
    def add_stock(stock_article: StockArticle, quantity: int, reference: str):
        if quantity <= 0:
            raise ValidationError("Menge muss größer als 0 sein.")
        StockMovement.objects.create(
            stock_article=stock_article,
            quantity=quantity,
            price=stock_article.price,
            movement_type=MovementType.IN,
            reference=reference
        )

    @staticmethod
    @transaction.atomic
    def _adjust_reserved(stock_article: StockArticle, quantity: int, action: str, reference: str):
        """
        Internal helper to reserve, release, or consume stock.
        """
        if quantity <= 0:
            return

        if action == "reserve":
            StockMovement.objects.create(
                stock_article=stock_article,
                quantity=quantity,
                price=stock_article.price,
                movement_type=MovementType.RESERVED,
                reference=reference
            )
            return

        # For 'release' or 'consume', reduce existing RESERVED movements FIFO
        reserved_movements = (
            StockMovement.objects
            .select_for_update()
            .filter(stock_article=stock_article, movement_type=MovementType.RESERVED)
            .order_by('created')
        )

        qty_to_adjust = quantity
        for mv in reserved_movements:
            if mv.quantity <= qty_to_adjust:
                qty_to_adjust -= mv.quantity
                mv.delete()
            else:
                mv.quantity -= qty_to_adjust
                mv.save(update_fields=['quantity'])
                qty_to_adjust = 0
                break

        if action == "consume":
            if qty_to_adjust > 0:
                StockMovement.objects.create(
                    stock_article=stock_article,
                    quantity=quantity - qty_to_adjust,
                    price=stock_article.price,
                    movement_type=MovementType.USED,
                    reference=reference
                )

    @staticmethod
    def reserve_stock(stock_article: StockArticle, quantity: int, reference: str):
        StockService._adjust_reserved(stock_article, quantity, 'reserve', reference)

    @staticmethod
    def release_reserved(stock_article: StockArticle, quantity: int, reference: str):
        """
        Public method to release reserved stock back to available.
        """
        StockService._adjust_reserved(stock_article, quantity, 'release', reference)

    @staticmethod
    def consume_reserved(stock_article: StockArticle, quantity: int, reference: str):
        StockService._adjust_reserved(stock_article, quantity, 'consume', reference)


class DeliveryService:
    """
    Handles delivery check-in and adds stock movements for delivered items.
    """

    @staticmethod
    @transaction.atomic
    def check_in_delivery(delivery):
        """
        Check in a delivery:
        - Create or lock StockArticle per article/price
        - Add delivered quantity via StockMovement
        - Mark delivery and delivery articles as checked_in
        """
        if delivery.checked_in:
            raise ValidationError("Lieferung wurde bereits eingebucht.")

        delivery_articles = delivery.articles.select_for_update().select_related("article")

        for da in delivery_articles:
            if da.checked_in:
                continue

            # Get or create the StockArticle for this article & price
            sa, _ = StockArticle.objects.get_or_create(article=da.article, price=da.price)

            # Lock the StockArticle row for concurrency safety
            sa = StockArticle.objects.select_for_update().get(pk=sa.pk)

            # Add delivered quantity
            StockService.add_stock(
                stock_article=sa,
                quantity=da.quantity,
                reference=f"Lieferung {delivery.delivery_number}"
            )

            # Mark delivery article as checked in
            da.checked_in = timezone.now()
            da.save(update_fields=["checked_in"])

        # Mark delivery as checked in
        delivery.checked_in = timezone.now()
        delivery.save(update_fields=["checked_in"])


class DemandService:
    @staticmethod
    @transaction.atomic
    def update_demands():
        # Platzhalter für zukünftige Logik
        pass
