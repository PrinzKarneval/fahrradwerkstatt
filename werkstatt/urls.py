from django.urls import path
from .views import *

urlpatterns = [
    # Customer
    path('customers/', CustomerList.as_view(), name='customer_list'),
    path('customers/<int:pk>', CustomerDetail.as_view(), name='customer_detail'),
    path('customers/create', CustomerCreate.as_view(), name='customer_create'),
    path('customers/<int:pk>/update', CustomerUpdate.as_view(), name='customer_update'),

    # RepairOrder
    path('repair-orders/', RepairOrderList.as_view(), name='repair_order_list'),
    path('repair-orders/create/<int:pk>', RepairOrderCreate.as_view(), name='repair_order_create'),
    path('repair-orders/<int:pk>', RepairOrderDetail.as_view(), name='repair_order_detail'),
    path('repair-orders/<int:pk>/update', RepairOrderUpdate.as_view(), name='repair_order_update'),
    path('repair-orders/<int:pk>/delete', RepairOrderDelete.as_view(), name='repair_order_delete'),
    path('repair-orders/<int:pk>/finish', RepairOrderFinish.as_view(), name='repair_order_finish'),
    path('repair-orders/<int:pk>/pay', InvoiceCreateFromRepairOrder.as_view(), name='repair_order_pay'),

    # RepairOrderService
    path('repair-orders/<int:pk>/service-add', RepairOrderServiceAdd.as_view(), name='repair_order_service_add'),
    path('repair-orders/<int:order_pk>/service/<int:pk>/update', RepairOrderServiceUpdate.as_view(),
         name='repair_order_service_update'),
    path('repair-orders/<int:order_pk>/service/<int:pk>/delete', RepairOrderServiceDelete.as_view(),
         name='repair_order_service_delete'),

    # RepairOrderArticle
    path('repair-orders/<int:pk>/article/add', RepairOrderArticleAdd.as_view(), name='repair_order_article_add'),
    path('repair_order_article_plus_one/<int:roa_pk>/', repair_order_article_plus_one, name= 'repair_order_article_plus_one'),
    path('repair_order_article_minus_one/<int:roa_pk>/', repair_order_article_minus_one, name= 'repair_order_article_minus_one'),
    path('repair-orders/<int:order_pk>/article/<int:pk>/update', RepairOrderArticleUpdate.as_view(),
         name='repair_order_article_update'),
    path('repair-orders/<int:order_pk>/article/<int:pk>/delete', RepairOrderArticleDelete.as_view(),
         name='repair_order_article_delete'),

    # Invoice
    path('invoice/<int:pk>', InvoiceDetail.as_view(), name='invoice_detail'),
    path('invoice/<int:pk>/print', InvoicePrint.as_view(), name='invoice_print'),

    # Inventory
    path('inventory/', Inventory.as_view(), name='inventory')

]
