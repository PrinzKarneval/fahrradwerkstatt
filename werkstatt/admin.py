from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.forms import BaseInlineFormSet

from .services import RepairOrderHandler, SupplyOrderHandler

admin.site.site_header = 'Workshop Admin'
admin.site.site_title = 'Workshop Admin Portal'
admin.site.index_title = 'Willkommen in der Workshop Verwaltung'

from django.contrib import admin
from .models import *


# ---------------------------
# Article Inlines
# ---------------------------
class ArticleInline(admin.TabularInline):
    model = Article
    extra = 0
    readonly_fields = ['description']


class StockArticleInline(admin.TabularInline):
    model = StockArticle
    extra = 0
    readonly_fields = ['price', 'quantity']


# ---------------------------
# Invoice Inlines
# ---------------------------
class InvoiceArticleInline(admin.TabularInline):
    model = InvoiceArticle
    extra = 0
    readonly_fields = ['manufacturer', 'type', 'name', 'description', 'ean', 'price', 'quantity']
    can_delete = False

    def has_add_permission(self, request, obj):
        return False


class InvoiceServiceInline(admin.TabularInline):
    model = InvoiceService
    extra = 0
    readonly_fields = [
        'main_category', 'sub_category', 'number', 'name', 'children_bike', 'hub_gear', 'derailleur',
        'mtb', 'road_bike', 'cargo_bike', 'hub_engine', 'mid_engine', 'price', 'quantity'
    ]
    can_delete = False

    def has_add_permission(self, request, obj):
        return False


class InvoiceInline(admin.StackedInline):
    model = Invoice
    extra = 0
    inlines = [InvoiceArticleInline, InvoiceServiceInline]
    can_delete = False

    def has_add_permission(self, request, obj):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------------------------
# SupplyOrder Inlines
# ---------------------------
class SupplyOrderArticleInline(admin.TabularInline):
    model = SupplyOrderArticle
    extra = 0

    def has_delete_permission(self, request, obj=None):
        return not (obj and (obj.submitted or obj.delivered))

    def has_add_permission(self, request, obj=None):
        return not (obj and (obj.submitted or obj.delivered))

    def has_change_permission(self, request, obj=None):
        return not (obj and (obj.submitted or obj.delivered))


# ---------------------------
# RepairOrder Inlines
# ---------------------------
class RepairOrderArticleInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        seen = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue

            sa = form.cleaned_data.get("stock_article")
            if not sa:
                continue

            if sa.pk in seen:
                raise ValidationError(
                    "Jeder Artikel darf pro Reparaturauftrag nur einmal vorkommen."
                )
            seen.add(sa.pk)


class RepairOrderArticleInline(admin.TabularInline):
    model = RepairOrderArticle
    formset = RepairOrderArticleInlineFormSet
    extra = 1
    readonly_fields = ['price', 'total', 'installed']

    def price(self, obj):
        return obj.stock_article.article.price

    def total(self, obj):
        return self.price(obj) * obj.quantity

    def has_delete_permission(self, request, obj=None):
        return True  # erlaubt löschen, Reservations/Requests werden automatisch angepasst

    def has_add_permission(self, request, obj=None):
        return True


class RepairOrderServiceInline(admin.TabularInline):
    model = RepairOrderService
    extra = 1


class RepairOrderInline(admin.StackedInline):
    model = RepairOrder
    extra = 0



@admin.register(ArticleType)
class ArticleTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent']
    inlines = [ArticleInline]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['name', 'manufacturer', 'type', 'price']
    list_filter = ['manufacturer', 'type']
    inlines = [StockArticleInline]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email']
    ordering = ['name']
    inlines = [RepairOrderInline, InvoiceInline]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['customer', 'date_paid', 'serial_number']
    list_filter = ['customer']
    inlines = [InvoiceArticleInline, InvoiceServiceInline]


@admin.register(RepairOrder)
class RepairOrderAdmin(admin.ModelAdmin):
    list_display = ['pk', 'customer', 'date_created', 'date_finished', 'serial_number']
    list_filter = ['customer', 'date_created', 'date_finished']
    actions = ['create_invoice', 'reserve_articles']
    inlines = [RepairOrderArticleInline, RepairOrderServiceInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)

        old_quantities = {
            obj.pk: obj.quantity
            for obj in formset.queryset
            if isinstance(obj, RepairOrderArticle)
        }

        deleted = [
            obj for obj in formset.deleted_objects
            if isinstance(obj, RepairOrderArticle)
        ]

        # Jetzt speichern
        for obj in instances:
            obj.save()

        for obj in deleted:
            obj.delete()

        formset.save_m2m()

        def on_commit():
            # Deletes
            for obj in deleted:
                RepairOrderHandler.update_quantity(
                    ro=obj.order,
                    sa=obj.stock_article,
                    old_quantity=obj.quantity,
                    new_quantity=0
                )

            # Creates + Updates
            for obj in instances:
                if not isinstance(obj, RepairOrderArticle):
                    continue

                old = old_quantities.get(obj.pk, 0)
                if old != obj.quantity:
                    RepairOrderHandler.update_quantity(
                        ro=obj.order,
                        sa=obj.stock_article,
                        old_quantity=old,
                        new_quantity=obj.quantity
                    )

        transaction.on_commit(on_commit)

    def create_invoice(self, request, queryset):
        count = 0
        for item in queryset:
            item.create_invoice()
            count += 1
        self.message_user(request, f"{count} Auftrag(s) erfolgreich in Rechnung erstellt.", messages.SUCCESS)

    def reserve_articles(self, request, queryset):
        total_reserved = 0
        for item in queryset:
            for ro in item.articles.all():
                result = ro.reserve_articles()
                if result:
                    total_reserved += result['NEW_RESERVATIONS']
        self.message_user(request, f"{total_reserved} Artikel erfolgreich reserviert.", messages.SUCCESS)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'main_category', 'sub_category', 'number', 'children_bike', 'hub_gear',
                    'derailleur', 'mtb', 'road_bike', 'cargo_bike', 'hub_engine', 'mid_engine']


@admin.register(WorkRate)
class WorkRateAdmin(admin.ModelAdmin):
    list_display = ['start', 'rate']


admin.site.register(Manufacturer)


@admin.register(SupplyOrder)
class SupplyOrderAdmin(admin.ModelAdmin):
    list_display = ['pk', 'vendor', 'status', 'submitted', 'delivered']
    list_filter = ['vendor', 'submitted', 'delivered']
    inlines = [SupplyOrderArticleInline]

    def get_readonly_fields(self, request, obj=None):
        return ['modified'] if obj and obj.delivered else ['modified']

    def has_delete_permission(self, request, obj=None):
        return obj and not obj.submitted


@admin.register(SupplyOrderArticleReceived)
class SupplyOrderArticleReceivedAdmin(admin.ModelAdmin):
    actions = ['check_in']

    def check_in(self, request, queryset):
        for order in queryset:
            SupplyOrderHandler.check_in(order)


@admin.register(StockArticleRequest)
class StockArticleRequestAdmin(admin.ModelAdmin):
    list_display = ['get_order', 'stock_article', 'quantity']
    fields = ['get_order', 'stock_article', 'get_sa_price', 'quantity', 'created']

    def get_order(self, obj):
        return obj.repair_order_article.order

    get_order.short_description = 'Reparaturauftrag'

    def get_sa_price(self, obj):
        return str(obj.stock_article.price) + " €"

    get_sa_price.short_description = 'Preis'

    def has_change_permission(self, request, obj=...):
        return False

    def has_delete_permission(self, request, obj=...):
        return False


@admin.register(StockArticleReservation)
class StockArticleReservationAdmin(admin.ModelAdmin):
    list_display = ('get_order', 'stock_article', 'get_sa_price', 'quantity', 'status')
    fields = ['get_order', 'stock_article', 'get_sa_price', 'quantity', 'status']

    def get_order(self, obj):
        return obj.repair_order_article.order

    get_order.short_description = 'Reparaturauftrag'

    def get_sa_price(self, obj):
        return str(obj.stock_article.price) + " €"

    get_sa_price.short_description = 'Preis'

    def has_change_permission(self, request, obj=...):
        return False

    def has_delete_permission(self, request, obj=...):
        return False


admin.site.register(Vendor)
