from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from lager.services import StockService
from werkstatt.models import *

admin.site.register(Customer)

@admin.register(StockArticleReservation)
class StockArticleReservationAdmin(admin.ModelAdmin):
    list_display = ('stock_article', 'repair_order_article', 'quantity')
    search_fields = ('stock_article__article__name', 'repair_order_article__id')


@admin.register(StockArticleRequest)
class StockArticleRequestAdmin(admin.ModelAdmin):
    list_display = ('stock_article', 'repair_order_article', 'quantity', 'created')
    search_fields = ('stock_article__article__name', 'repair_order_article__id')
    list_filter = ('created',)

class RepairOrderArticleInline(admin.TabularInline):
    model = RepairOrderArticle
    extra = 0

    readonly_fields = ('stock_article',)

    def save_model(self, request, obj, form, change):
        """
        Ensure stock reservations are updated when adding/removing articles.
        """
        super().save_model(request, obj, form, change)


class RepairOrderServiceInline(admin.TabularInline):
    model = RepairOrderService
    extra = 0



@admin.register(RepairOrder)
class RepairOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'date_created', 'date_finished', 'bike_type')
    list_filter = ('bike_type', 'date_created', 'date_finished')
    search_fields = ('customer__name', 'bike_model', 'serial_number')
    inlines = [RepairOrderArticleInline, RepairOrderServiceInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        # Automatically reserve stock for each article
        order = form.instance
        for roa in order.articles.select_for_update().select_related('stock_article'):
            sa = roa.stock_article
            reserved_qty = sa.get_reserved_quantity()
            needed_qty = roa.quantity

            if needed_qty > reserved_qty:
                delta = needed_qty - reserved_qty
                StockService.reserve_stock(stock_article=sa, quantity=delta, reference=f"RO #{order.pk}")
            elif needed_qty < reserved_qty:
                delta = reserved_qty - needed_qty
                StockService.release_reserved(stock_article=sa, quantity=delta, reference=f"RO #{order.pk}")
class InvoiceArticleInline(admin.TabularInline):
    model = InvoiceArticle
    extra = 0

class InvoiceServiceInline(admin.TabularInline):
    model = InvoiceService
    extra = 0

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'date_paid', 'bike_type')
    list_filter = ('date_paid', 'bike_type')
    search_fields = ('customer__name', 'bike_model', 'serial_number')
    inlines = [InvoiceArticleInline, InvoiceServiceInline]

    actions = ['finalize_invoice']

    @admin.action(description="Rechnung abschließen und Reservierungen verbrauchen")
    def finalize_invoice(self, request, queryset):
        for invoice in queryset:
            try:
                # Consume reserved stock for all articles
                for ia in invoice.articles.select_for_update().select_related('invoice', 'invoicearticle'):
                    sa = StockArticle.objects.filter(article__ean=ia.ean, price=ia.price).first()
                    if sa:
                        StockService.consume_reserved(stock_article=sa, quantity=ia.quantity,
                                                      reference=f"Invoice #{invoice.pk}")
                self.message_user(request, f"Rechnung #{invoice.pk} abgeschlossen.", level=messages.SUCCESS)
            except ValidationError as e:
                self.message_user(request, f"Fehler bei Rechnung #{invoice.pk}: {e}", level=messages.ERROR)


@admin.register(WorkRate)
class WorkRateAdmin(admin.ModelAdmin):
    list_display = ('rate', 'start_date', 'end_date')
    list_filter = ('start_date', 'end_date')
    search_fields = ('rate',)
