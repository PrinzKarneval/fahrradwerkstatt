from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from lager.models import MovementType
from lager.services import StockService, DemandService


class RepairOrderPricingService:
    """Calculate prices for services and total order."""

    @staticmethod
    def calculate_service_price(ros) -> Decimal:
        from werkstatt.models import WorkRate
        work_value = ros.get_work_value()
        work_rate = WorkRate.get_current_rate()
        return (work_value / Decimal(10)) * work_rate

    @staticmethod
    def get_total_services_price(order) -> Decimal:
        return sum(
            RepairOrderPricingService.calculate_service_price(s)
            for s in order.services.all()
        )

    @staticmethod
    def get_total(repair_order) -> Decimal:
        return RepairOrderPricingService.get_total_services_price(repair_order) + repair_order.get_total_article_price()


class RepairOrderHandler:
    """Handles quantity updates for RepairOrderArticles."""

    @staticmethod
    @transaction.atomic
    def update_quantity(order, stock_article, new_qty: int):
        from werkstatt.models import RepairOrderArticle
        roa, _ = RepairOrderArticle.objects.get_or_create(
            order=order,
            stock_article=stock_article,
            defaults={"quantity": 0}
        )

        if new_qty <= 0:
            roa.quantity = 0
            roa.save(update_fields=["quantity"])
            DemandService.sync_repair_order_article(roa)
            roa.delete()
            return

        roa.quantity = new_qty
        roa.save(update_fields=["quantity"])
        DemandService.sync_repair_order_article(roa)


class RepairOrderLifecycleService:
    """Handles finishing and deleting repair orders."""

    @staticmethod
    @transaction.atomic
    def finish_order(order):
        for roa in order.articles.select_for_update().select_related("stock_article"):
            StockService.consume_reserved(
                stock_article=roa.stock_article,
                quantity=roa.quantity,
                reference=f"RO #{order.pk}"
            )
            from werkstatt.models import StockArticleReservation
            StockArticleReservation.objects.filter(
                repair_order_article=roa
            ).delete()
        order.delete()


class InvoiceCreationService:
    """Handles creation and cancellation of invoices."""

    @staticmethod
    @transaction.atomic
    def create_invoice(order):
        # Check for open stock requests
        from werkstatt.models import StockArticleRequest, InvoiceArticle, Invoice, InvoiceService

        if StockArticleRequest.objects.filter(repair_order_article__order=order).exists():
            raise ValidationError("Auftrag hat noch offene Materialanforderungen.")

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

        # Invoice Articles
        invoice_articles = [
            InvoiceArticle(
                manufacturer=roa.stock_article.article.manufacturer,
                stock_article=roa.stock_article,
                type=roa.stock_article.article.type,
                name=roa.stock_article.article.name,
                description=roa.stock_article.article.description,
                ean=roa.stock_article.article.ean,
                price=roa.stock_article.article.price,
                invoice=invoice,
                quantity=roa.quantity
            )
            for roa in order.articles.all()
        ]
        InvoiceArticle.objects.bulk_create(invoice_articles)

        # Invoice Services
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

        # Consume reserved stock
        for roa in order.articles.select_for_update().select_related("stock_article"):
            StockService.create_movement(
                stock_article=roa.stock_article,
                quantity=roa.quantity,
                movement_type=MovementType.OUT_SOLD,
                reference=f"RO #{order.pk}"
            )

        order.delete()
        return invoice

    @staticmethod
    @transaction.atomic
    def cancel_invoice(invoice):
        for ia in invoice.articles.select_related("stock_article").all():
            if ia.stock_article:
                StockService.create_movement(
                    stock_article=ia.stock_article,
                    quantity=ia.quantity,
                    movement_type=MovementType.IN_STORNO,
                    reference=f"Storno Invoice #{invoice.pk}"
                )
        invoice.delete()
