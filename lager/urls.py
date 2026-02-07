from django.urls import path

from .views import *

urlpatterns = [
    path('', InventoryView.as_view(), name='inventory'),
    path('bestellungen', SupplyOrdersView.as_view(), name='supply_orders'),
    path('lieferungen', DeliveriesView.as_view(), name='deliveries'),
]