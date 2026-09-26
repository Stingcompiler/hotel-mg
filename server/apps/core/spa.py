"""The built SPA served by Django (spec §2, F3): ``static_spa/`` is copied from ``web/dist`` at release time.

Hashed files under ``assets/`` are cached for a year; every other path that is not the API returns
``index.html`` so the client router can open it (``/stays/…``, ``/print/…``).
"""

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.views.static import serve

NOT_BUILT = (
    '<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>Sky Towers</title>'
    '<body style="font-family:sans-serif;padding:48px"><h1>واجهة البرنامج غير مبنية بعد</h1>'
    "<p>شغّل <code>python build/build_spa.py</code> من جذر المستودع ثم أعد تحميل الصفحة.</p></body></html>"
)


def asset(request, path):
    response = serve(request, path, document_root=settings.SPA_ROOT / "assets")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def index(request, path=""):
    root = settings.SPA_ROOT
    if path:
        try:  # a top-level file of the build (icons); serve() refuses paths outside the root
            return serve(request, path, document_root=root)
        except (Http404, SuspiciousFileOperation):
            pass
    page = root / "index.html"
    if not page.is_file():
        return HttpResponse(NOT_BUILT, status=503, content_type="text/html; charset=utf-8")
    response = FileResponse(page.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"  # new builds load at once; the assets it names are immutable
    return response
