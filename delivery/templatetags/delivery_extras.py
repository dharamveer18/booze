from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Usage: {{ my_dict|get_item:key }}"""
    return dictionary.get(key, 0)
