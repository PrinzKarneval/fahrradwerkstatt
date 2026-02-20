from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from lager.models import StockMovement, MovementType, StockArticle, STOCK_OUT, Article


class StockService:
    @staticmethod
    @transaction.atomic
    def create_movement(stock_article: StockArticle, quantity: int, movement_type: MovementType, reference: str):
        if quantity <= 0:
            return

        if movement_type not in dict(MovementType.choices):
            raise ValidationError('Ungültiger Bewegungstyp')

        if movement_type in STOCK_OUT:
            available = stock_article.get_available_quantity()
            if available <= 0:
                raise ValidationError('Lagerartikel ist nicht verfügbar')
            elif available < quantity:
                raise ValidationError(f"Nur '{available}' Einheiten von '{stock_article}' sind verfügbar")

        StockMovement.objects.create(
            stock_article=stock_article,
            quantity=quantity,
            price=stock_article.price,
            movement_type=movement_type,
            reference=reference
        )
        return


class DeliveryService:
    @staticmethod
    def _get_locked_stock_article(da, is_correction):
        lookup = {"article": da.article, "price": da.price}

        if is_correction:
            try:
                return StockArticle.objects.select_for_update().get(**lookup)
            except StockArticle.DoesNotExist:
                raise ValidationError(f"Lagerartikel '{da.article}' mit Preis {da.price} existiert nicht")
        else:
            sa, _ = StockArticle.objects.select_for_update().get_or_create(**lookup)
            return sa

    @staticmethod
    @transaction.atomic
    def check_in_delivery(delivery):
        if delivery.checked_in:
            raise ValidationError('Lieferung wurde bereits eingebucht')

        delivery_articles = delivery.articles.select_for_update().select_related('article')

        if len(delivery_articles) == 0:
            raise ValidationError("Keine Artikel in Lieferung vorhanden")

        touched_stock_articles = set()

        for da in delivery_articles:
            sa = DeliveryService._get_locked_stock_article(da, is_correction=delivery.is_correction)

            if delivery.is_correction:
                sa_available = sa.get_available_quantity()
                if sa_available < da.quantity:
                    raise ValidationError(f"Korrektur nicht möglich, nur {sa_available} von {da.quantity} vorhanden")

            touched_stock_articles.add(sa)
            mt = MovementType.OUT_CORRECTION if delivery.is_correction else MovementType.IN_DELIVERY
            StockService.create_movement(
                stock_article=sa,
                quantity=da.quantity,
                movement_type=mt,
                reference=f'Lieferung {delivery.delivery_number}')

        delivery.checked_in = timezone.now()
        delivery.save(update_fields=['checked_in'])
        DemandService.update_demands(list(touched_stock_articles))


class DemandService:
    @staticmethod
    @transaction.atomic
    def update_demands(stock_articles):
        from werkstatt.models import ArticleRequest, StockArticleReservation
        """
        Aktualisiert alle offenen Requests für die übergebenen StockArticles.
        Verteilt verfügbare Mengen auf Reservations und reduziert Requests.
        """
        articles = {sa.article for sa in stock_articles}
        # Alle relevanten Requests abrufen
        requests = (
            ArticleRequest.objects
            .select_for_update(skip_locked=True)
            .filter(article__in=articles)
            .select_related('repair_order_article')
        )

        # StockArticles in Bulk abrufen, um mehrfaches select_for_update zu vermeiden
        sa_map = {
            sa.id: sa for sa in StockArticle.objects.select_for_update().filter(id__in=[s.id for s in stock_articles])
        }

        for req in requests:
            sa = sa_map[req.stock_article_id]

            available = sa.get_available_quantity()
            if available <= 0:
                continue

            missing = req.repair_order_article.get_missing_reservation_quantity()
            if missing <= 0:
                req.delete()
                continue

            reserve_qty = min(req.quantity, available, missing)
            if reserve_qty <= 0:
                continue

            # Reservation anlegen oder aktualisieren
            res, created = StockArticleReservation.objects.get_or_create(
                repair_order_article=req.repair_order_article,
                stock_article=sa,
                defaults={'quantity': 0})
            if not created:
                res = StockArticleReservation.objects.select_for_update().get(pk=res.pk)

            res.quantity += reserve_qty
            res.save(update_fields=['quantity'])

            # Request anpassen oder löschen
            req.quantity -= reserve_qty
            if req.quantity <= 0:
                req.delete()
            else:
                req.save(update_fields=['quantity'])

    @staticmethod
    @transaction.atomic
    def create_demands(ro):
        from werkstatt.models import ArticleRequest, StockArticleReservation, RepairOrderArticle
        """
        Erstellt / synchronisiert Reservations + Requests
        für alle RepairOrderArticles eines RepairOrders.
        """
        roas = (
            RepairOrderArticle.objects
            .select_for_update()
            .filter(order_id=ro.id)
            .select_related('stock_article')
        )

        if not roas.exists():
            return

        # Alle StockArticles in Bulk abrufen
        sa_map = {
            sa.id: sa for sa in StockArticle.objects.select_for_update().filter(
                id__in=[roa.stock_article_id for roa in roas]
            )
        }

        for roa in roas:
            sa = sa_map[roa.stock_article_id]

            # Reservation + Request in einem Schritt abrufen
            reservation = StockArticleReservation.objects.select_for_update().filter(repair_order_article=roa,
                stock_article=sa).first()
            request = ArticleRequest.objects.select_for_update().filter(repair_order_article=roa,
                                                                        stock_article=sa).first()

            reserved_qty = reservation.quantity if reservation else 0
            request_qty = request.quantity if request else 0
            needed = max(0, roa.quantity - (reserved_qty + request_qty))

            if needed <= 0:
                if request:
                    request.delete()
                continue

            available = sa.get_available_quantity() + reserved_qty
            reserve_qty = min(needed, available)
            request_qty_new = needed - reserve_qty

            # Reservation
            if reserve_qty > 0:
                if reservation:
                    reservation.quantity += reserve_qty
                    reservation.save(update_fields=['quantity'])
                else:
                    StockArticleReservation.objects.create(
                        repair_order_article=roa,
                        stock_article=sa,
                        quantity=reserve_qty
                    )

            # Request
            if request_qty_new > 0:
                if request:
                    request.quantity = request_qty_new
                    request.save(update_fields=['quantity'])
                else:
                    ArticleRequest.objects.create(
                        repair_order_article=roa,
                        stock_article=sa,
                        quantity=request_qty_new
                    )
            elif request:
                request.delete()

    @staticmethod
    @transaction.atomic
    def sync_repair_order_article(roa):
        from werkstatt.models import ArticleRequest, StockArticleReservation
        """
        Synchronisiert einen einzelnen RepairOrderArticle.
        """
        sa = StockArticle.objects.select_for_update().get(pk=roa.stock_article_id)

        reservation = StockArticleReservation.objects.select_for_update().filter(
            repair_order_article=roa,
            stock_article=sa
        ).first()
        request = ArticleRequest.objects.select_for_update().filter(
            repair_order_article=roa,
            stock_article=sa
        ).first()

        reserved_qty = reservation.quantity if reservation else 0
        request_qty = request.quantity if request else 0
        delta = roa.quantity - (reserved_qty + request_qty)

        # INCREASE
        if delta > 0:
            available = sa.get_available_quantity()
            to_reserve = min(delta, available)
            to_request = delta - to_reserve

            if to_reserve:
                if reservation:
                    reservation.quantity += to_reserve
                    reservation.save(update_fields=['quantity'])
                else:
                    StockArticleReservation.objects.create(
                        repair_order_article=roa,
                        stock_article=sa,
                        quantity=to_reserve
                    )

            if to_request:
                if request:
                    request.quantity += to_request
                    request.save(update_fields=['quantity'])
                else:
                    request = ArticleRequest.objects.create(
                        repair_order_article=roa,
                        stock_article=sa,
                        quantity=to_request
                    )

        # DECREASE
        elif delta < 0:
            reduce_qty = abs(delta)
            if request:
                req_reduce = min(request.quantity, reduce_qty)
                request.quantity -= req_reduce
                reduce_qty -= req_reduce
                if request.quantity <= 0:
                    request.delete()
                else:
                    request.save(update_fields=['quantity'])

            if reduce_qty > 0 and reservation:
                reservation.quantity -= reduce_qty
                if reservation.quantity <= 0:
                    reservation.delete()
                else:
                    reservation.save(update_fields=['quantity'])
