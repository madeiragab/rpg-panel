from rest_framework.throttling import AnonRateThrottle


class ThrottleDeToken(AnonRateThrottle):
    """Freio dos endereços de token.

    Herda de `AnonRateThrottle` de propósito: quem pede token ainda não está
    autenticado, então a conta é por IP. O `scope` aponta para a taxa "login"
    declarada em `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`.
    """

    scope = "login"
