from django import template

register = template.Library()


@register.filter
def div(value, arg):
    """Divide value by arg"""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0


@register.filter
def mul(value, arg):
    """Multiply value by arg"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def porcento(value):
    """Fração de 0 a 1 como porcentagem, com ponto decimal.

    Devolve string de propósito: número passa pela localização do template e,
    com LANGUAGE_CODE pt-br, "43.75" viraria "43,75" — que num `style` inline
    o navegador simplesmente ignora.
    """
    try:
        return f"{float(value) * 100:.2f}"
    except (TypeError, ValueError):
        return "0"
