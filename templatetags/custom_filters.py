from django import template

register = template.Library()

def getobjectattr(obj, field_name):
    """Returns the value of the specified field from the given object."""
    try:
        return getattr(obj, field_name)
    except AttributeError:
        return ''

register.filter("getobjectattr", getobjectattr)