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
    def update_quantity(order: "RepairOrder", stock_article: StockArticle, new_qty: int):
        """
        Update a RepairOrderArticle for a single StockArticle:
        - When increasing: reserve available stock first, then create requests
        - When decreasing: reduce requests first, then reservations
        """

        # Lock objects for this StockArticle
        sa = StockArticle.objects.select_for_update().get(pk=stock_article.pk)

        roa, _ = RepairOrderArticle.objects.select_for_update().get_or_create(
            order=order,
            stock_article=sa,
            defaults={"quantity": 0},
        )

        reservation = (
            StockArticleReservation.objects.select_for_update()
            .filter(repair_order_article=roa, stock_article=sa)
            .first()
        )

        request = (
            StockArticleRequest.objects.select_for_update()
            .filter(repair_order_article=roa, stock_article=sa)
            .first()
        )

        current_total = (reservation.quantity if reservation else 0) + (request.quantity if request else 0)

        if new_qty > current_total:
            # --- Increasing quantity ---
            delta = new_qty - current_total

            # Step 1: Add to reservation as much as available
            avail = sa.get_available_quantity()
            reserve_delta = min(avail, delta)
            request_delta = delta - reserve_delta

            if reserve_delta > 0:
                if not reservation:
                    reservation = StockArticleReservation.objects.create(
                        repair_order_article=roa, stock_article=sa, quantity=reserve_delta
                    )
                else:
                    reservation.quantity += reserve_delta
                    reservation.save(update_fields=["quantity"])

            if request_delta > 0:
                if not request:
                    request = StockArticleRequest.objects.create(
                        repair_order_article=roa, stock_article=sa, quantity=request_delta
                    )
                else:
                    request.quantity += request_delta
                    request.save(update_fields=["quantity"])

        elif new_qty < current_total:
            # --- Decreasing quantity ---
            delta = current_total - new_qty

            # Step 1: Reduce requests first
            if request:
                reduce_req = min(request.quantity, delta)
                request.quantity -= reduce_req
                delta -= reduce_req
                if request.quantity <= 0:
                    request.delete()
                    request = None
                else:
                    request.save(update_fields=["quantity"])

            # Step 2: Reduce reservations
            if delta > 0 and reservation:
                reduce_res = min(reservation.quantity, delta)
                reservation.quantity -= reduce_res
                if reservation.quantity <= 0:
                    reservation.delete()
                    reservation = None
                else:
                    reservation.save(update_fields=["quantity"])

        # --- Update or delete ROA ---
        total_assigned = (reservation.quantity if reservation else 0) + (request.quantity if request else 0)
        if total_assigned > 0:
            roa.quantity = total_assigned
            roa.save(update_fields=["quantity"])
        else:
            roa.delete()
