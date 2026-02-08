from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, TemplateView, DetailView, CreateView

from .models import *
from .services import StockService, DeliveryService


class InventoryView(ListView):
    model = Article
    context_object_name = 'articles'
    template_name = 'lager/inventory.html'


class ArticleDetail(DetailView):
    model = Article
    context_object_name = 'article'

class SupplyOrderList(ListView):
    model = SupplyOrder
    context_object_name = 'supply_orders'


class SupplyOrderDetail(DetailView):
    model = SupplyOrder
    context_object_name = 'supply_order'


class DeliveryList(ListView):
    model = Delivery
    context_object_name = 'deliveries'


class DeliveryDetail(DetailView):
    model = Delivery
    context_object_name = 'delivery'


class DeliveryArticleCreate(CreateView):
    model = DeliveryArticle
    fields = ['delivery', 'article', 'quantity', 'price']
    template_name = 'lager/delivery_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.delivery = get_object_or_404(Delivery, pk=self.kwargs['pk'])
        if self.delivery.checked_in:
            messages.warning(request, "This delivery has already been checked in. No new articles can be added.")
            return redirect('delivery_detail', pk=self.delivery.pk)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['articles'] = Article.objects.all()
        return context

    def get_initial(self):
        initial = super().get_initial()
        delivery = Delivery.objects.get(pk=self.kwargs['pk'])
        initial['delivery'] = delivery
        return initial

    def form_valid(self, form):
        form.instance.delivery = self.delivery
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('delivery_detail', kwargs={'pk': self.delivery.pk})


def check_in_delivery(request, pk):
    delivery = get_object_or_404(Delivery, pk=pk)
    DeliveryService.check_in_delivery(delivery)
    return HttpResponseRedirect(delivery.get_absolute_url())