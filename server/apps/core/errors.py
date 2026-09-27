"""API error shape: ``{"code": <stable machine code>, "detail": <Arabic message>}`` (spec §7)."""

from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404, HttpResponseNotFound, JsonResponse
from rest_framework import exceptions, status
from rest_framework.views import exception_handler

MESSAGES = {
    "clock_rollback": "تم اكتشاف رجوع في ساعة الجهاز. العمليات موقوفة حتى يوافق المدير.",
    "version_conflict": "عُدِّل هذا السجل من مكان آخر. أعد التحميل وحاول مرة أخرى.",
    "owner_read_only": "جهاز المالك للعرض فقط.",
    "setup_done": "تم إعداد حساب المدير من قبل؛ سجّل الدخول به.",
    "no_open_shift": "لا توجد وردية مفتوحة على هذا الجهاز.",
    "validation_error": "البيانات المدخلة غير صحيحة.",
    "parse_error": "تعذّر قراءة البيانات المرسلة.",
    "unsupported_media_type": "نوع المحتوى المرسل غير مدعوم.",
    "not_acceptable": "صيغة الاستجابة المطلوبة غير مدعومة.",
    "not_authenticated": "يجب تسجيل الدخول أولًا.",
    "authentication_failed": "بيانات الدخول غير صحيحة.",
    "account_locked": "الدخول مقفل مؤقتًا بعد 5 محاولات خاطئة. حاول لاحقًا أو اطلب من المدير فتح القفل.",
    "token_expired": "انتهت الجلسة. سجّل الدخول مرة أخرى.",
    "confirmation_required": "هذا الإجراء يتطلب إعادة إدخال كلمة المرور.",
    "permission_denied": "ليست لديك صلاحية لهذا الإجراء.",
    "invalid_room_transition": "لا يمكن نقل الغرفة إلى هذه الحالة.",
    "reason_required": "السبب مطلوب لهذا الإجراء.",
    "room_occupied": "لا يمكن إخراج غرفة مشغولة من الخدمة.",
    "invalid_image": "الملف ليس صورة صالحة أو أكبر من 10 ميغابايت.",
    "date_in_past": "تاريخ الوصول في الماضي.",
    "duration_too_long": "المدة أطول من سنة.",
    "pricing_choice_required": "اختر طريقة احتساب السعر.",
    "room_unavailable": "الغرفة غير متاحة لهذه الفترة.",
    "room_type_mismatch": "الغرفة المختارة ليست من نوع الغرفة المطلوب.",
    "invalid_reservation_status": "لا يمكن تنفيذ هذا الإجراء على الحجز في حالته الحالية.",
    "override_invalid": "كلمة مرور المدير غير صحيحة.",
    "override_required": "هذا الإجراء يحتاج موافقة المدير (كلمة المرور والسبب).",
    "offline": "لا يوجد اتصال بالإنترنت — النسخ المحلية محفوظة وسيُعاد الرفع تلقائيًا.",
    "drive_not_linked": "لم يُربط حساب Drive.",
    "drive_not_configured": "ملف إعداد Drive غير موجود على هذا الجهاز.",
    "drive_error": "تعذّر الاتصال بـ Drive.",
    "task_closed": "أُغلقت هذه المهمة بإجراء سابق.",
    "snooze_limit": "استُنفدت مرات التأجيل؛ اختر إجراءً آخر.",
    "check_in_not_allowed": "لا يمكن التسكين خارج فترة الحجز.",
    "room_not_ready": "الغرفة ليست جاهزة للتسكين.",
    "room_required": "اختر غرفة قبل التسكين.",
    "not_found": "العنصر غير موجود.",
    "method_not_allowed": "هذا الإجراء غير مسموح.",
    "throttled": "محاولات كثيرة. انتظر قليلًا ثم حاول مرة أخرى.",
    "server_unavailable": "تعذّر الاتصال بالخادم المحلي. تأكد أن خدمة Sky Towers تعمل ثم حاول مرة أخرى.",
    "no_hotel": (
        "هذا الجهاز مضبوط كجهاز المالك ولم يستورد نسخة بعد. إن كان جهاز الاستقبال فشغّل "
        "«skytowers-server.exe init --role reception --force» ثم أعد تشغيل الخدمة."
    ),
    "error": "حدث خطأ غير متوقع.",
}


class ApiError(exceptions.APIException):
    """Raise from services/views with a stable ``code``; the Arabic ``detail`` comes from MESSAGES."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, code: str, status_code: int | None = None, detail: str | None = None, **extra):
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail=detail or MESSAGES.get(code, MESSAGES["error"]), code=code)
        self.error_code = code
        self.extra = extra  # machine-readable context, e.g. attempts_left


class VersionConflict(ApiError):
    def __init__(self):
        super().__init__("version_conflict", status.HTTP_409_CONFLICT)


def error_body(code: str, detail: str | None = None, **extra) -> dict:
    return {"code": code, "detail": detail or MESSAGES.get(code, MESSAGES["error"]), **extra}


def error_json_response(code: str, status_code: int) -> JsonResponse:
    """For middleware, which runs outside DRF's exception handling."""
    return JsonResponse(error_body(code), status=status_code, json_dumps_params={"ensure_ascii": False})


def api_not_found(request, exception=None):
    """Django-level 404 (no matching URL, or a missing hashed asset): JSON under ``/api/``, plain text otherwise."""
    if request.path.startswith("/api/"):
        return error_json_response("not_found", 404)
    return HttpResponseNotFound("Not found", content_type="text/plain; charset=utf-8")


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        if isinstance(exc, ImproperlyConfigured) and "hotel_id" in str(exc):
            # An owner PC with no hotel yet asked to write hotel data (e.g. a login event): a clear 409, not a 500.
            from rest_framework.response import Response

            return Response(error_body("no_hotel"), status=status.HTTP_409_CONFLICT)
        return None

    if isinstance(exc, ApiError):
        response.data = error_body(exc.error_code, str(exc.detail), **exc.extra)
        if exc.error_code == "override_invalid":
            # The service's transaction has already rolled back here, so the failed attempt survives.
            from apps.accounts.services import register_override_failure

            register_override_failure()
    elif isinstance(exc, exceptions.ValidationError):
        response.data = error_body("validation_error", errors=exc.detail)
    elif isinstance(exc, exceptions.APIException):
        code = exc.get_codes() if isinstance(exc.get_codes(), str) else exc.default_code
        response.data = error_body(code if code in MESSAGES else "error")
    elif isinstance(exc, Http404):
        response.data = error_body("not_found")
    elif isinstance(exc, DjangoPermissionDenied):
        response.data = error_body("permission_denied")
    return response
