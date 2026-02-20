from django.contrib import admin, messages
from django.db import transaction

from werkstatt.models import *
from werkstatt.services import RepairOrderHandler, InvoiceCreationService

admin.site.register(Customer)
admin.site.register(Manufacturer)


class RepairOrderArticleInline(admin.TabularInline):
    model = RepairOrderArticle
    extra = 0


class RepairOrderServiceInline(admin.TabularInline):
    model = RepairOrderService
    extra = 0


@admin.register(RepairOrder)
class RepairOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'date_created', 'date_finished', 'is_ebike')
    list_filter = ('is_ebike', 'date_created', 'date_finished')
    search_fields = ('customer__name', 'bike_model', 'serial_number')
    inlines = [RepairOrderArticleInline, RepairOrderServiceInline]

    @transaction.atomic
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        for roa in obj.articles.select_related('stock_article').all():
            RepairOrderHandler.update_quantity(obj, roa.stock_article, roa.quantity)


admin.site.register(ServiceCategory)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'number', 'normal_price', 'ebike_price')
    list_filter = ('category',)
    search_fields = ('name',)


@admin.register(StockArticleReservation)
class StockArticleReservationAdmin(admin.ModelAdmin):
    list_display = ('stock_article', 'repair_order_article', 'quantity')
    search_fields = ('stock_article__article__name', 'repair_order_article__id')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ArticleRequest)
class ArticleRequestAdmin(admin.ModelAdmin):
    list_display = ('article', 'repair_order_article', 'quantity')
    search_fields = ('article__name', 'repair_order_article__id')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
            InvoiceCreationService.create_invoice(invoice)
