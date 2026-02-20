from django import forms

from werkstatt.models import RepairOrder, RepairOrderArticle, RepairOrderService, Customer, Invoice

select_date_field = forms.DateField(
    widget=forms.SelectDateWidget(
        empty_label=("Tag", "Monat", "Jahr"),
        attrs={'class': 'form-control d-inline w-auto mx-1'}  # Bootstrap classes
    ),
    label="Datum auswählen"
)


class CustomerCreateForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = '__all__'


class CustomerUpdateForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = '__all__'


class InvoiceForm(forms.ModelForm):
    date_paid = select_date_field

    class Meta:
        model = Invoice
        fields = ["date_paid"]


class RepairOrderForm(forms.ModelForm):
    class Meta:
        model = RepairOrder
        exclude = ['date_created', 'date_finished', 'invoice']
        fields = [
            "customer",
            "description",
            "is_ebike",
            "manufacturer",
            "bike_model",
            "color",
            "serial_number",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})
        self.fields['customer'].disabled = True
        self.fields['customer'].widget.attrs.update({'class': 'form-control'})


class RepairOrderArticleForm(forms.ModelForm):
    class Meta:
        model = RepairOrderArticle
        exclude = ["order"]


class RepairOrderServiceForm(forms.ModelForm):
    class Meta:
        model = RepairOrderService
        fields = ["service", "quantity"]


class RepairOrderFinishForm(forms.ModelForm):
    date_finished = select_date_field

    class Meta:
        model = RepairOrder
        fields = ['date_finished']
