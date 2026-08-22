from django import template

register = template.Library()


@register.filter
def sum(obj, field):
    """
    Sum the values of a specific field in a list of dictionaries or objects.
    """
    if not obj:
        return 0.0
    
    try:
        total = 0.0
        for item in obj:
            # Check if item is a dictionary or an object
            if isinstance(item, dict):
                if field in item:
                    total += float(item[field] or 0)
            else:
                # Assume it's an object with attribute access
                value = getattr(item, field, 0)
                total += float(value or 0)
        
        return total
    except Exception as e:
        return 0.0
