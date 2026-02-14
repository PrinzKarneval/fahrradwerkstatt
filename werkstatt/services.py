from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from lager.services import StockService
from werkstatt.models import (
    RepairOrder, RepairOrderArticle, RepairOrderService,
    Invoice, InvoiceArticle, InvoiceService,
    StockArticleReservation, StockArticleRequest,
    WorkRate
)
from lager.models import StockArticle, StockMovement, MovementType


class InvoiceCreationService:
    @staticmethod
    @transaction.atomic
    def create_invoice(order: RepairOrder) -> Invoice:
        invoice = Invoice.objects.create(
            date_paid=timezone.now(),
            customer=order.customer,
            postal=order.customer.postal,
            city=order.customer.city,
            street=order.customer.street,
            str_no=order.customer.str_no,
            description=order.description,
            bike_type=order.bike_type,
            bike_model=order.bike_model,
            color=order.color,
            serial_number=order.serial_number,
        )

        # Articles
        invoice_articles = [
            InvoiceArticle(
                manufacturer=roa.stock_article.article.manufacturer,
                type=roa.stock_article.article.type,
                name=roa.stock_article.article.name,
                description=roa.stock_article.article.description,
                ean=roa.stock_article.article.ean,
                price=roa.stock_article.article.price,
                invoice=invoice,
                quantity=roa.quantity,
            )
            for roa in order.articles.all()
        ]
        InvoiceArticle.objects.bulk_create(invoice_articles)

        # Services
        invoice_services = [
            InvoiceService(
                main_category=ros.service.main_category,
                sub_category=ros.service.sub_category,
                number=ros.service.number,
                name=ros.service.name,
                children_bike=ros.service.children_bike,
                hub_gear=ros.service.hub_gear,
                derailleur=ros.service.derailleur,
                mtb=ros.service.mtb,
                road_bike=ros.service.road_bike,
                cargo_bike=ros.service.cargo_bike,
                hub_engine=ros.service.hub_engine,
                mid_engine=ros.service.mid_engine,
                invoice=invoice,
                quantity=ros.quantity,
                price=RepairOrderPricingService.calculate_service_price(ros)
            )
            for ros in order.services.all()
        ]
        InvoiceService.objects.bulk_create(invoice_services)

        # ✅ Consume reserved stock for all articles

        for roa in order.articles.select_for_update().select_related('stock_article'):
            StockService.consume_reserved(
                stock_article=roa.stock_article,
                quantity=roa.quantity,
                reference=f"RO #{order.pk} Invoice #{invoice.pk}"
            )

        order.delete()
        return invoice


class RepairOrderPricingService:
    @staticmethod
    def calculate_service_price(ros: RepairOrderService) -> Decimal:
        work_value = ros.get_work_value()
        work_rate = WorkRate.get_current_rate()
        return (work_value / Decimal(10)) * work_rate

    @staticmethod
    def get_total_services_price(order: RepairOrder) -> Decimal:
        return sum(RepairOrderPricingService.calculate_service_price(s) for s in order.services.all())

    @staticmethod
    def get_total(order: RepairOrder) -> Decimal:
        return RepairOrderPricingService.get_total_services_price(order) + order.get_total_article_price()


class RepairOrderHandler:
    @staticmethod
    @transaction.atomic
    def update_quantity(order, stock_article: StockArticle, new_qty: int):
        """
        Adjust quantity of a stock article on a repair order.

        - Reserving available stock first
        - Creating requests for any remainder if stock insufficient
        - Reducing requests first when lowering quantity, then releasing reservations
        """
        # Lock stock article and ROA for concurrency
        sa = StockArticle.objects.select_for_update().get(pk=stock_article.pk)
        roa, created = RepairOrderArticle.objects.get_or_create(
            order=order,
            stock_article=sa,
            defaults={"quantity": 0}
        )

        current_qty = roa.quantity
        delta = new_qty - current_qty  # positive = increase, negative = decrease

        if delta > 0:
            # Increasing quantity
            available = sa.get_available_quantity()
            to_reserve = min(delta, available)
            to_request = delta - to_reserve

            if to_reserve > 0:
                StockService.reserve_stock(
                    stock_article=sa,
                    quantity=to_reserve,
                    reference=f"RO #{order.pk}"
                )

            if to_request > 0:
                req, _ = StockArticleRequest.objects.get_or_create(
                    repair_order_article=roa,
                    stock_article=sa,
                    defaults={"quantity": 0}
                )
                req.quantity += to_request
                req.save(update_fields=['quantity'])

        elif delta < 0:
            # Decreasing quantity
            remaining_to_reduce = abs(delta)

            # 1️⃣ Reduce outstanding requests first
            req = StockArticleRequest.objects.filter(
                repair_order_article=roa,
                stock_article=sa
            ).first()
            if req:
                if req.quantity <= remaining_to_reduce:
                    remaining_to_reduce -= req.quantity
                    req.delete()
                else:
                    req.quantity -= remaining_to_reduce
                    req.save(update_fields=['quantity'])
                    remaining_to_reduce = 0

            # 2️⃣ If still remaining, release reserved stock
            if remaining_to_reduce > 0:
                reserved = sa.get_reserved_quantity()
                to_release = min(remaining_to_reduce, reserved)
                if to_release > 0:
                    StockService.release_reserved(
                        stock_article=sa,
                        quantity=to_release,
                        reference=f"RO #{order.pk}"
                    )

        # Update or delete ROA
        if new_qty > 0:
            roa.quantity = new_qty
            roa.save(update_fields=['quantity'])
        else:
            roa.delete()