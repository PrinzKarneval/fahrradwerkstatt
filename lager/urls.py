from django.urls import path

from lager.views import Inventory

urlpatterns = [
    path('', Inventory.as_view(), name='inventory'),
]