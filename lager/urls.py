from django.urls import path

from .views import *

urlpatterns = [
    path('lager', InventoryView.as_view(), name='inventory'),
    path('artikel/<int:pk>', ArticleDetail.as_view(), name='article_detail'),
    path('bestellungen/', SupplyOrderList.as_view(), name='supply_order_list'),
    path('bestellungen/<int:pk>', SupplyOrderDetail.as_view(), name='supply_order_detail'),
    path('lieferungen/', DeliveryList.as_view(), name='delivery_list'),
    path('lieferungen/<int:pk>', DeliveryDetail.as_view(), name='delivery_detail'),
    path('lieferungen/<int:pk>/neuer_artikel', DeliveryArticleCreate.as_view(), name='delivery_article_create'),
    path('lieferungen/<int:pk>/check_in', check_in_delivery, name='check_in_delivery'),
]