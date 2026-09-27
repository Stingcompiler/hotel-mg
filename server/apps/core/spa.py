"""The built SPA served by Django (spec §2, F3): ``static_spa/`` is copied from ``web/dist`` at release time.

Hashed files under ``assets/`` are cached for a year; every other path that is not the API returns
``index.html`` so the client router can open it (``/stays/…``, ``/print/…``).
"""

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.views.static import serve


def not_built_page(root) -> str:
    """The 503 page when ``static_spa/index.html`` is missing: says which process looked where, so a support call can
    tell a source checkout without a build from an installed service, or another server holding the port."""
    import platform
    import sys

    frozen = getattr(sys, "frozen", False)
    hint = (
        "شغّل <code>python build/build_spa.py</code> من جذر المستودع ثم أعد تحميل الصفحة."
        if not frozen
        else "أعد تثبيت البرنامج من المثبّت الرسمي؛ المجلد أدناه يجب أن يحتوي <code>index.html</code>."
    )
    other = (
        "إن كان لديك خادم آخر يعمل من الشيفرة المصدرية على المنفذ 8471 فأوقفه أولًا "
        "(<code>netstat -ano | findstr :8471</code>)."
    )
    return (
        '<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>Sky Towers</title>'
        '<body style="font-family:sans-serif;padding:48px"><h1>واجهة البرنامج غير مبنية بعد</h1>'
        f'<p>{hint}</p><p style="color:#555">{other}</p>'
        f'<pre dir="ltr" style="text-align:left;color:#555">SPA_ROOT = {root}\nexecutable = {sys.executable}\n'
        f"frozen = {bool(frozen)}\nhost = {platform.node()}</pre></body></html>"
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
        return HttpResponse(not_built_page(root), status=503, content_type="text/html; charset=utf-8")
    response = FileResponse(page.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"  # new builds load at once; the assets it names are immutable
    return response
