from django.db import models
from werkstatt.models import Customer


class Appointments(models.Model):
    NEW = 1
    CONFIRMED = 2
    REJECTED = 3
    DONE = 4
    CANCELLED = 5
    STATUS = (
        (NEW, 'New'),
        (CONFIRMED, 'Confirmed'),
        (REJECTED, 'Rejected'),
        (DONE, 'Done'),
        (CANCELLED, 'Cancelled'),
    )

    INSPECTION = 1
    REPAIR = 2
    VALUE_CHECK = 3

    TYPE = (
        (INSPECTION, 'Inspektion'),
        (REPAIR, 'Reparatur'),
        (VALUE_CHECK, 'Kostenvoranschlag')
    )

    status = models.IntegerField(choices=STATUS, default=NEW)
    type = models.IntegerField(choices=STATUS, default=NEW)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='appointments', blank=True, null=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=25)
    postal = models.CharField(max_length=10)
    city = models.CharField(max_length=100)
    street = models.CharField(max_length=100)
    str_nr = models.CharField(max_length=20)
    start = models.DateTimeField(blank=True, null=True)
    end = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return (f'{self.first_name} {self.last_name}')

