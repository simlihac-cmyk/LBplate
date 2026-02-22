from django.conf import settings


def analytics(request):
    return {
        'GA4_MEASUREMENT_ID': getattr(settings, 'GA4_MEASUREMENT_ID', ''),
        'ADSENSE_CLIENT_ID': getattr(settings, 'ADSENSE_CLIENT_ID', ''),
    }
