from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from lager.models import (
    ArticleType, Article, StockMovement, Vendor,
    SupplyOrderArticle, SupplyOrder, Manufacturer,
    Delivery, DeliveryArticle, StockArticle
)
from lager.services import DeliveryService


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'country')
    search_fields = ('name', 'email', 'phone')


@admin.register(ArticleType)
class ArticleTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('name', 'manufacturer', 'type', 'price', 'minimum')
    list_filter = ('type', 'manufacturer')
    search_fields = ('name',)


@admin.register(StockArticle)
class StockArticleAdmin(admin.ModelAdmin):
    list_display = ('article', 'price', 'quantity', 'get_available_quantity')
    readonly_fields = ('get_available_quantity', )

    def get_available_quantity(self, obj):
        return obj.get_available_quantity()
    get_available_quantity.short_description = "Verfügbar"

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('stock_article', 'quantity', 'movement_type', 'reference', 'created')
    list_filter = ('movement_type',)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SupplyOrderArticleInline(admin.TabularInline):
    model = SupplyOrderArticle
    extra = 0


@admin.register(SupplyOrder)
class SupplyOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'vendor', 'ordered')
    list_filter = ('created', 'ordered')
    search_fields = ('vendor__name',)
    inlines = [SupplyOrderArticleInline]
    actions = ['submit_orders', 'reopen_orders']

    @admin.action(description="Ausgewählte Bestellungen einreichen")
    def submit_orders(self, request, queryset):
        for order in queryset:
            if not order.ordered:
                order.submit()
                self.message_user(request, f"Bestellung #{order.pk} eingereicht.", level=messages.SUCCESS)
            else:
                self.message_user(request, f"Bestellung #{order.pk} war bereits eingereicht.", level=messages.WARNING)

    @admin.action(description="Ausgewählte Bestellungen erneut öffnen")
    def reopen_orders(self, request, queryset):
        for order in queryset:
            if order.ordered:
                order.ordered = None
                order.save(update_fields=['ordered'])
                self.message_user(request, f"Bestellung #{order.pk} erneut geöffnet.", level=messages.SUCCESS)
            else:
                self.message_user(request, f"Bestellung #{order.pk} war nicht eingereicht.", level=messages.WARNING)

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.ordered)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.ordered)


class DeliveryArticleInline(admin.TabularInline):
    model = DeliveryArticle
    fields = ('article', 'quantity', 'price')
    extra = 1


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'order', 'delivery_number', 'delivery_date', 'checked_in')
    inlines = [DeliveryArticleInline]
    actions = ['check_in']

    @admin.action(description="Ausgewählte Lieferungen ins Lager einbuchen")
    def check_in(self, request, queryset):
        for delivery in queryset:
            try:
                DeliveryService.check_in_delivery(delivery)
                self.message_user(
                    request,
                    f"Lieferung {delivery.delivery_number} erfolgreich eingebucht.",
                    level=messages.SUCCESS
                )
            except ValidationError as e:
                self.message_user(
                    request,
                    f"Lieferung {delivery.delivery_number} konnte nicht eingebucht werden: {e}",
                    level=messages.ERROR
                )

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.checked_in)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.checked_in)

