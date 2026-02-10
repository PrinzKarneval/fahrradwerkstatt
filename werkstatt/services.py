from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from werkstatt.models import (
    RepairOrder, RepairOrderArticle, RepairOrderService,
    Invoice, InvoiceArticle, InvoiceService,
    StockArticleReservation, StockArticleRequest,
    WorkRate
)
from lager.models import StockArticle, StockMovement


class InvoiceCreationService:
    @staticmethod
    @transaction.atomic
    def create_invoice(order: RepairOrder) -> Invoice:
        """
        Erstellt eine Rechnung aus einem RepairOrder inkl. Artikel und Services.
        Löscht den RepairOrder nach erfolgreicher Erstellung.
        """
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
        order.delete()
        return invoice

"""        for roa in order.articles.all():
            sa = roa.stock_article
            if sa.get_available_quantity() >= roa.quantity:
                StockMovement.objects.create(
                    stock_article=sa,
                    quantity=roa.quantity,
                    movement_type=StockMovement.OUT,
                    reference=f"RO #{order.pk} Rechnung #{invoice.pk}"
                )
"""


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
    def update_quantity(order: RepairOrder, stock_article: StockArticle, old_qty: int, new_qty: int):
        roa, _ = RepairOrderArticle.objects.select_for_update().get_or_create(
            order=order,
            stock_article=stock_article,
            defaults={"quantity": old_qty},
        )
        difference = new_qty - roa.quantity
        if difference > 0:
            RepairOrderHandler._increase_quantity(roa, difference)
        elif difference < 0:
            RepairOrderHandler._reduce_quantity(roa, -difference)

    @staticmethod
    def _increase_quantity(roa: RepairOrderArticle, added_quantity: int):
        sa = StockArticle.objects.select_for_update().get(pk=roa.stock_article_id)
        available = sa.get_available_quantity()
        reserve_qty = min(available, added_quantity)
        request_qty = added_quantity - reserve_qty

        if reserve_qty:
            StockArticleReservation.objects.update_or_create(
                repair_order_article=roa,
                stock_article=sa,
                defaults={'quantity': reserve_qty}
            )
        if request_qty:
            StockArticleRequest.objects.update_or_create(
                repair_order_article=roa,
                stock_article=sa,
                defaults={'quantity': request_qty}
            )

        roa.quantity += added_quantity
        roa.save(update_fields=['quantity'])

    @staticmethod
    def _reduce_quantity(roa: RepairOrderArticle, reduction: int):
        sa = StockArticle.objects.select_for_update().get(pk=roa.stock_article_id)
        requested = StockArticleRequest.objects.select_for_update().filter(
            repair_order_article=roa, stock_article=sa).first()
        reservation = StockArticleReservation.objects.select_for_update().filter(
            repair_order_article=roa, stock_article=sa).first()

        if requested:
            reduce_request = min(requested.quantity, reduction)
            requested.quantity -= reduce_request
            requested.save()
            reduction -= reduce_request
            if requested.quantity <= 0:
                requested.delete()

        if reduction > 0 and reservation:
            reduce_reserve = min(reservation.quantity, reduction)
            reservation.quantity -= reduce_reserve
            reservation.save()
            if reservation.quantity <= 0:
                reservation.delete()

        roa.quantity -= reduction
        roa.save()
        if roa.quantity <= 0:
            roa.delete()
