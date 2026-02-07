from django.views.generic import ListView

from .models import *


class Inventory(ListView):
    model = Article
    context_object_name = 'articles'
    template_name = 'lager/inventory.html'