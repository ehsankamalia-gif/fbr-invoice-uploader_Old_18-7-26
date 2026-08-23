def feature_flags(request):
    """Context processor for feature flags."""
    return {
        'enable_portal': True,
    }
