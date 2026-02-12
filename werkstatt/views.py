from django.contrib import messages
from django.db.models import Exists, OuterRef
from django.http import *
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import CreateView, ListView, DetailView, UpdateView, DeleteView
from django.urls import reverse_lazy

from lager.models import Article, StockArticle
from .forms import *
from .mixins import BackLinkMixin, TitleMixin
from .models import *
from .services import RepairOrderHandler

class CustomerList(ListView):
    model = Customer
    context_object_name = 'customers'


class CustomerDetail(DetailView):
    model = Customer

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        fields = Customer._meta.fields
        context['fields'] = fields
        context['num_fields'] = len(fields)
        return context


class CustomerCreate(CreateView):
    model = Customer
    form_class = CustomerCreateForm
    template_name = 'werkstatt/form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_link'] = reverse('customer_list')
        return context

    def get_success_url(self):
        return reverse_lazy('customer_detail', args=[self.object.pk])


class CustomerUpdate(UpdateView):
    model = Customer
    form_class = CustomerUpdateForm
    template_name = 'werkstatt/form.html'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Kunde aktualisieren"
        context['back_link'] = reverse_lazy("customer_detail", args=[self.object.pk])
        return context

    def get_success_url(self):
        return reverse_lazy('customer_detail', args=[self.object.pk])


class CustomerDelete(DeleteView):
    model = Customer
    success_url = reverse_lazy('customer-list')
    template_name = 'delete.html'


class RepairOrderList(ListView):
    model = RepairOrder
    template_name = 'repair_order_list.html'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Aufträge"
        fields = RepairOrder._meta.fields
        context['columns'] = fields
        context['num_fields'] = len(fields)
        return context


class RepairOrderDetail(DetailView):
    model = RepairOrder

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_link'] = reverse_lazy('customer_detail', args=[self.object.customer.pk])
        context['title'] = f"Auftrag {context['object']}"
        return context


class RepairOrderCreate(CreateView):
    model = RepairOrder
    template_name = 'werkstatt/form.html'
    form_class = RepairOrderForm

    def get_initial(self):
        initial = super().get_initial()
        customer = get_object_or_404(Customer, pk=self.kwargs.get("pk"))
        initial['customer'] = customer
        return initial

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)
        context["back_link"] = reverse_lazy("customer_detail", args=[self.kwargs.get('pk')])
        context['title'] = "Auftrag erstellen"
        return context

    def form_valid(self, form):
        form.instance.customer = get_object_or_404(Customer, pk=self.kwargs.get('pk'))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('repair_order_detail', args=[self.object.pk])


class RepairOrderUpdate(TitleMixin, BackLinkMixin, UpdateView):
    model = RepairOrder
    form_class = RepairOrderForm
    template_name = 'form.html'
    title = "Auftrag bearbeiten"
    back_link = lambda self: reverse_lazy('repair_order_detail', args=[self.object.pk])


class RepairOrderDelete(DeleteView):
    model = RepairOrder
    template_name = 'delete.html'

    def get_success_url(self):
        return reverse_lazy('customer_detail', args=[self.object.customer.pk])


class RepairOrderServiceAdd(TitleMixin, BackLinkMixin, CreateView):
    model = RepairOrderService
    form_class = RepairOrderServiceForm
    template_name = "form.html"
    title = "Service hinzufügen"
    back_link = lambda self: reverse_lazy('repair_order_detail', args=[self.object.pk])

    def form_valid(self, form):
        order = get_object_or_404(RepairOrder, pk=self.kwargs["pk"])
        service = order.repairorderservice_set.filter(service=form.instance.service).first()
        if service:
            service.quantity += form.instance.quantity
            service.save(update_fields=["quantity"])
            return HttpResponseRedirect(reverse_lazy('repair_order_detail', args=[order.pk]))
        form.instance.order = order
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('repair_order_detail', kwargs={'pk': self.object.order.pk})


class RepairOrderServiceUpdate(UpdateView):
    model = RepairOrderService
    form_class = RepairOrderServiceForm
    template_name = "form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["back_link"] = reverse_lazy("repair_order_detail", args=[self.kwargs.get('order_pk')])
        context["title"] = "Service aktualisieren"
        return context

    def get_success_url(self):
        return reverse_lazy('repair_order_detail', kwargs={'pk': self.object.order.pk})


class RepairOrderServiceDelete(DeleteView):
    model = RepairOrderService
    template_name = 'ro_article_delete.html'

    def get_success_url(self):
        return reverse_lazy('repair_order_detail', kwargs={'pk': self.object.order.pk})


def repair_order_article_plus_one(request, roa_pk):
    roa = get_object_or_404(RepairOrderArticle, pk=roa_pk)
    RepairOrderHandler.update_quantity(roa.order, roa.stock_article, roa.quantity + 1)
    return HttpResponseRedirect(reverse_lazy('repair_order_detail', args=[roa.order.pk]))

def repair_order_article_minus_one(request, roa_pk):
    roa = get_object_or_404(RepairOrderArticle, pk=roa_pk)
    RepairOrderHandler.update_quantity(roa.order, roa.stock_article, roa.quantity - 1)
    return HttpResponseRedirect(reverse_lazy('repair_order_detail', args=[roa.order.pk]))


class RepairOrderArticleAdd(CreateView):
    model = RepairOrderArticle
    form_class = RepairOrderArticleForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order_pk"] = self.kwargs.get("pk")
        context["back_link"] = reverse_lazy("repair_order_detail", args=[self.kwargs.get('pk')])
        context["title"] = "Artikel hinzufügen"
        return context

    def form_valid(self, form):
        ro = get_object_or_404(RepairOrder, pk=self.kwargs['pk'])
        roa, created = RepairOrderArticle.objects.get_or_create(
            order=ro,
            stock_article=form.instance.stock_article,
            defaults={'quantity': 0}
        )
        sa = form.cleaned_data['stock_article']
        RepairOrderHandler.update_quantity(ro, sa , roa.quantity + form.instance.quantity)
        return HttpResponseRedirect(reverse('repair_order_detail', args=[self.kwargs.get('pk')], context={"messages": "adskjla"}))

    def get_success_url(self):
        return reverse('repair_order_detail', args=[self.kwargs['pk']])

class RepairOrderArticleUpdate(UpdateView):
    model = RepairOrderArticle
    form_class = RepairOrderArticleForm
    template_name = "werkstatt/form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order_pk"] = context["object"].order.pk
        context["back_link"] = reverse("repair_order_detail", args=[self.kwargs.get('order_pk')])
        context["title"] = "Artikel aktualisieren"
        return context

    def form_valid(self, form):
        roa = RepairOrderArticle.objects.get(pk=form.instance.pk)
        print("Old quantity", roa.quantity)
        print("New quantity", form.instance.quantity)
        RepairOrderHandler.update_quantity(
            form.instance.order,
            form.instance.stock_article,
            roa.quantity,
            form.instance.quantity)

        return HttpResponseRedirect(reverse('repair_order_detail', args=[roa.order.pk]))


class RepairOrderArticleDelete(DeleteView):
    model = RepairOrderArticle
    template_name = 'ro_article_delete.html'

    def get_success_url(self):
        return reverse_lazy('repair_order_detail', kwargs={'pk': self.object.order.pk})


class RepairOrderFinish(UpdateView):
    model = RepairOrder
    form_class = RepairOrderFinishForm
    template_name = "form.html"

    def get_initial(self):
        initial = super().get_initial()
        if "date_finished" not in initial.keys():
            initial["date_finished"] = timezone.now()
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Fertigstellungsdatum eingeben"
        context["back_link"] = reverse_lazy("repair_order_detail", args=[self.kwargs.get('pk')])
        return context

    def get_success_url(self):
        return reverse_lazy('repair_order_detail', kwargs={'pk': self.object.pk})


class InvoiceCreateFromRepairOrder(CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = "form.html"

    def get_initial(self):
        initial = super().get_initial()
        order = get_object_or_404(RepairOrder, pk=self.kwargs.get("pk"))
        initial["customer"] = order.customer
        initial["postal"] = order.customer.postal
        initial["city"] = order.customer.city
        initial["street"] = order.customer.street
        initial["str_no"] = order.customer.str_no
        initial["serial_number"] = order.serial_number
        initial["date_paid"] = timezone.now()
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Rechnungsdatum eingeben"
        context["back_link"] = reverse_lazy("repair_order_detail", args=[self.kwargs.get('pk')])
        return context

    def form_valid(self, form):
        repair_order = get_object_or_404(RepairOrder, pk=self.kwargs.get("pk"))
        customer = repair_order.customer
        form.instance.customer = customer
        form.instance.postal = customer.postal
        form.instance.city = customer.city
        form.instance.street = customer.street
        form.instance.str_no = customer.str_no
        form.instance.description = repair_order.description
        form.instance.bike_type = repair_order.bike_type
        form.instance.bike_model = repair_order.bike_model
        form.instance.color = repair_order.color
        form.instance.serial_number = repair_order.serial_number

        response = super().form_valid(form)
        self.create_invoice_articles(repair_order, self.object)
        self.create_invoice_services(repair_order, self.object)
        repair_order.repairorderarticle_set.all().delete()
        repair_order.repairorderservice_set.all().delete()
        repair_order.delete()
        return response

    @staticmethod
    def create_invoice_articles(repair_order, invoice):
        repair_order_articles = repair_order.repairorderarticle_set.all()
        for roa in repair_order_articles:
            InvoiceArticle.objects.create(
                manufacturer=roa.stock_article.manufacturer,
                type=roa.stock_article.type,
                name=roa.stock_article.name,
                description=roa.stock_article.description,
                ean=roa.stock_article.ean,
                price=roa.stock_article.price,
                invoice=invoice,
                quantity=roa.quantity,
            )

    @staticmethod
    def create_invoice_services(repair_order, invoice):
        repair_order_services = repair_order.repairorderservice_set.all()
        work_rate = WorkRate.get_current_rate()
        for ros in repair_order_services:
            InvoiceService.objects.create(
                invoice=invoice,
                main_category=ros.service.main_category,
                sub_category=ros.service.sub_category,
                number=ros.service.number,
                name=ros.service.name,
                children_bike=ros.service.children_bike,
                hub_gear=ros.service.hub_gear,
                derailleur=ros.service.derailleur,
                mtb=ros.service.mtb,
                road_bike=ros.service.road_bike,
                cargo_bike=ros.service.cargo_bike,
                hub_engine=ros.service.hub_engine,
                mid_engine=ros.service.mid_engine,
                quantity=ros.quantity,
                price=ros.get_total(),
            )

    def get_success_url(self):
        return reverse_lazy('invoice_detail', args=[self.object.pk])


class InvoiceDetail(DetailView):
    model = Invoice

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["back_link"] = reverse_lazy("customer_detail", kwargs={"pk": self.object.customer.pk})
        return context


class InvoicePrint(DetailView):
    model = Invoice
    template_name = "invoice_print.html"


class Inventory(ListView):
    model = Article
    context_object_name = 'articles'
    template_name = 'werkstatt/inventory.html'

    def get_queryset(self):
        return Article.objects.all()


def article_filter(request, pk):
    """Initial page with the filter form."""
    context = {
        "title": "Artikel hinzufügen",
        "types": ArticleType.objects.all(),
        "pk": pk,
        "back_link": reverse('repair_order_detail', args=[pk]),
    }
    return render(request, "article_filter.html", context)


def filter_manufacturers(request):
    """Return manufacturers that have articles of the selected type."""
    type_id = request.GET.get("type")
    manufacturers = Manufacturer.objects.filter(
        Exists(Article.objects.filter(type_id=type_id, manufacturer=OuterRef("pk")))
    )
    return render(request, "partials/manufacturer_select.html", {"manufacturers": manufacturers})


def filter_articles(request):
    """Return articles filtered by type + manufacturer."""
    type_id = request.GET.get("type")
    manufacturer_id = request.GET.get("manufacturer")

    articles = Article.objects.all()
    if type_id:
        articles = articles.filter(type_id=type_id)
    if manufacturer_id:
        articles = articles.filter(manufacturer_id=manufacturer_id)

    return render(request, "partials/article_list.html", {"articles": articles})


def repair_order_add_article(request, pk):
    repair_order = get_object_or_404(RepairOrder, pk=pk)

    if request.method == "POST":
        stock_article = get_object_or_404(StockArticle, pk=request.POST.get("article"))
        repair_order.add_article(repair_order, stock_article)
        messages.success(request, f"You selected: {stock_article}")
    return redirect(repair_order.get_absolute_url())
