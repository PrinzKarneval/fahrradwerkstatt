"""from django.contrib import admin

from lager.services import StockArticleHandler
from werkstatt.models import *
from werkstatt.services import RepairOrderHandler

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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        StockArticleHandler.handle_repair_order_article_change(obj)

    def delete_model(self, request, obj):
        StockArticleHandler.handle_repair_order_article_change(obj, deleted=True)
        super().delete_model(request, obj)

class RepairOrderServiceInline(admin.TabularInline):
    model = RepairOrderService
    extra = 0


@admin.register(RepairOrder)
class RepairOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'date_created', 'date_finished', 'bike_type')
    list_filter = ('bike_type', 'date_created', 'date_finished')
    search_fields = ('customer__name', 'bike_model', 'serial_number')
    inlines = [RepairOrderArticleInline, RepairOrderServiceInline]

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


@admin.register(WorkRate)
class WorkRateAdmin(admin.ModelAdmin):
    list_display = ('rate', 'start_date', 'end_date')
    list_filter = ('start_date', 'end_date')
    search_fields = ('rate',)
"""