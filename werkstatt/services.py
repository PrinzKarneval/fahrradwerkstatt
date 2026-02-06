from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from werkstatt.models import Invoice, InvoiceArticle, RepairOrderArticle, StockArticle, StockArticleReservation, \
    StockArticleRequest, RepairOrderService, WorkRate, InvoiceService, RepairOrder


RESERVATION_RESERVED = 1
RESERVATION_INSTALLED = 2
RESERVATION_CANCELLED = 3


class InvoiceCreationService:
    @staticmethod
    @transaction.atomic
    def create_invoice(order) -> None:
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

        # Create the InvoiceArticles
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
            ) for roa in order.articles.all()
        ]
        InvoiceArticle.objects.bulk_create(invoice_articles)

        # Create the InvoiceServices
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
                price=RepairOrderPricingService.calculate_service_price(ros),
            ) for ros in order.services.all()
        ]
        InvoiceService.objects.bulk_create(invoice_services)

        # Delete the RepairOrder
        order.delete()
        return None


class RepairOrderPricingService:
    @staticmethod
    def calculate_service_price(ros: RepairOrderService) -> Decimal:
        work_value = ros.get_work_value()
        work_rate = WorkRate.get_current_rate()
        return (work_value / Decimal(10)) * work_rate

    @staticmethod
    def get_total_services_price(repair_order) -> Decimal:
        total = Decimal(0.0)
        for s in repair_order.services.all():
            total += RepairOrderPricingService.calculate_service_price(s)
        return total

    @staticmethod
    def get_total(repair_order) -> Decimal:
        return (
                RepairOrderPricingService.get_total_services_price(repair_order)
                + repair_order.get_total_article_price()
        )


class RepairOrderHandler:
    @staticmethod
    @transaction.atomic
    def add_new_roa_to_order(ro: RepairOrder, sa: StockArticle, quantity: int) -> None:
        roa, created = RepairOrderArticle.objects.get_or_create(order=ro, stock_article=sa)
        RepairOrderHandler.roa_increase_quantity(roa, quantity)

    @staticmethod
    def roa_increase_quantity(roa: RepairOrderArticle, new_quantity: int) -> None:
        added_quantity = new_quantity - roa.quantity
        if added_quantity <= 0:
            return None
        sa = StockArticle.objects.select_for_update().get(pk=roa.stock_article_id)
        available_quantity = sa.get_available_quantity()
        reservable_quantity = min(available_quantity, added_quantity)
        missing = added_quantity - reservable_quantity

        reservation = (StockArticleReservation.objects.select_for_update()
                       .filter(repair_order_article=roa, stock_article=sa).first())
        requested = (StockArticleRequest.objects.select_for_update()
                     .filter(repair_order_article=roa, stock_article=sa).first())

        if reservable_quantity:
            # Reserve as much as possible from available stock
            if reservation:
                StockArticleReservation.objects.filter(pk=reservation.pk).update(quantity=F('quantity') + reservable_quantity)
            else:
                StockArticleReservation.objects.create(
                    repair_order_article=roa,
                    stock_article=sa,
                    quantity=reservable_quantity)
        if missing:
            if requested:
                StockArticleRequest.objects.filter(pk=requested.pk).update(quantity=F('quantity') + missing)
            else:
                StockArticleRequest.objects.create(
                    repair_order_article=roa,
                    stock_article=sa,
                    quantity=missing)

        roa.quantity += added_quantity
        roa.save(update_fields=['quantity'])
        return None

"""
class ReservationHandler:

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
"""