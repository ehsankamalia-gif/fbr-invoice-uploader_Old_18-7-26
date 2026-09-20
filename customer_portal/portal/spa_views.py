from django.conf import settings
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def spa_shell_view(request, *args, **kwargs):
    """Serves the Vue 3 SPA shell for every migrated URL. Accepts and ignores
    any captured URL parameters (e.g. <int:customer_id>) - Vue Router reads
    the real params from window.location client-side; this view only needs
    to guarantee the csrftoken cookie is set (via ensure_csrf_cookie) before
    any login POST, since the SPA has no server-rendered {% csrf_token %}
    form to set it implicitly."""
    return render(request, 'spa/shell.html', {
        'spa_build_version': settings.SPA_BUILD_VERSION,
    })
