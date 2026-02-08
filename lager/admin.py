from django.contrib import admin

from lager.models import ArticleType, Article, Service, StockMovement, Vendor, SupplyOrderArticle, \
    SupplyOrder, Manufacturer, Delivery, DeliveryArticle, StockArticle
from lager.services import StockService, DeliveryService


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
    list_display = ('article', 'quantity', 'price')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('stock_article', 'quantity', 'movement_type', 'reference', 'created')
    list_filter = ('movement_type',)


class SupplyOrderArticleInline(admin.TabularInline):
    model = SupplyOrderArticle
    extra = 0
    inlines = []


@admin.register(SupplyOrder)
class SupplyOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'vendor', 'ordered')
    list_filter = ('created', 'ordered')
    search_fields = ('vendor__name',)
    inlines = [SupplyOrderArticleInline]
    actions = ['submit_orders', 'reopen_orders']

    def submit_orders(self, request, queryset):
        for order in queryset:
            order.submit()

    def reopen_orders(self, request, queryset):
        for order in queryset:
            order.submitted = None
            order.save()

    submit_orders.short_description = "Ausgewählte Bestellungen einreichen"
    reopen_orders.short_description = "Ausgewählte Bestellungen erneut öffnen"

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
    list_display = ('vendor', 'order', 'delivery_number', 'delivery_date')
    inlines = [DeliveryArticleInline]
    actions = ['check_in']

    def check_in(self, request, queryset):
        for delivery in queryset:
            DeliveryService.check_in_delivery(delivery)

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.checked_in)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.checked_in)


@admin.register(DeliveryArticle)
class DeliveryArticleAdmin(admin.ModelAdmin):
    list_display = ('delivery', 'article', 'quantity', 'checked_in')
    actions = ['check_in']

    def check_in(self, request, queryset):
        for delivery in queryset:
            delivery.check_in()

    check_in.short_description = "Ausgewählte Lieferartikel ins Lager überführen"

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.checked_in)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.checked_in)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'main_category', 'sub_category', 'number')
    list_filter = ('main_category', 'sub_category')
    search_fields = ('name',)
