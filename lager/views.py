from django.views.generic import ListView, TemplateView

from .models import *


class InventoryView(ListView):
    model = Article
    context_object_name = 'articles'
    template_name = 'lager/inventory.html'


class SupplyOrdersView(TemplateView):
    template_name = 'lager/supply_orders.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['supply_orders'] = SupplyOrder.objects.all()
        return context


class DeliveriesView(TemplateView):
    template_name = 'lager/deliveries.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['deliveries'] = Delivery.objects.all()
        return context