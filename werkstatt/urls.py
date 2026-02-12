from django.urls import path
from .views import *

urlpatterns = [
    # Customer
    path('', CustomerList.as_view(), name='customer_list'),
    path('kunden/<int:pk>', CustomerDetail.as_view(), name='customer_detail'),
    path('kunden/create', CustomerCreate.as_view(), name='customer_create'),
    path('kunden/<int:pk>/update', CustomerUpdate.as_view(), name='customer_update'),

    # RepairOrder
    path('auftraege/', RepairOrderList.as_view(), name='repair_order_list'),
    path('auftraege/create/<int:pk>', RepairOrderCreate.as_view(), name='repair_order_create'),
    path('auftraege/<int:pk>', RepairOrderDetail.as_view(), name='repair_order_detail'),
    path('auftraege/<int:pk>/update', RepairOrderUpdate.as_view(), name='repair_order_update'),
    path('auftraege/<int:pk>/delete', RepairOrderDelete.as_view(), name='repair_order_delete'),
    path('auftraege/<int:pk>/finish', RepairOrderFinish.as_view(), name='repair_order_finish'),
    path('auftraege/<int:pk>/pay', InvoiceCreateFromRepairOrder.as_view(), name='repair_order_pay'),

    # RepairOrderService
    path('auftraege/<int:pk>/service-add', RepairOrderServiceAdd.as_view(), name='repair_order_service_add'),
    path('auftraege/<int:order_pk>/service/<int:pk>/update', RepairOrderServiceUpdate.as_view(),
         name='repair_order_service_update'),
    path('auftraege/<int:order_pk>/service/<int:pk>/delete', RepairOrderServiceDelete.as_view(),
         name='repair_order_service_delete'),

    # RepairOrderArticle
    path('auftraege/<int:pk>/article/add', RepairOrderArticleAdd.as_view(), name='repair_order_article_add'),
    path('repair_order_article_plus_one/<int:roa_pk>/', repair_order_article_plus_one, name= 'repair_order_article_plus_one'),
    path('repair_order_article_minus_one/<int:roa_pk>/', repair_order_article_minus_one, name= 'repair_order_article_minus_one'),
    path('auftraege/<int:order_pk>/article/<int:pk>/update', RepairOrderArticleUpdate.as_view(),
         name='repair_order_article_update'),
    path('auftraege/<int:order_pk>/article/<int:pk>/delete', RepairOrderArticleDelete.as_view(),
         name='repair_order_article_delete'),

    # Invoice
    path('rechnungen/<int:pk>', InvoiceDetail.as_view(), name='invoice_detail'),
    path('rechnungen/<int:pk>/print', InvoicePrint.as_view(), name='invoice_print'),
]
