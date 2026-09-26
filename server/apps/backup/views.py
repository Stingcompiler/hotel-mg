from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsManager
from apps.accounts.services import require_confirmation
from apps.audit import services as audit
from apps.core.errors import ApiError

from . import drive, export, keys, merge, rules, services
from .models import BackupRun, ImportRun
from .serializers import (
    AuthUrlSerializer,
    BackupRunSerializer,
    BackupSettingsSerializer,
    BackupSettingsUpdateSerializer,
    CandidateSerializer,
    DriveImportSerializer,
    DriveStatusSerializer,
    ImportRequestSerializer,
    ImportRunSerializer,
    OwnerStatusSerializer,
    SyncResultSerializer,
)


class BackupRunView(APIView):
    """«نسخة احتياطية الآن» (artboard 6.13): writes the encrypted file now; the result line shows it."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={201: BackupRunSerializer})
    def post(self, request):
        run = export.run_backup(request.user, BackupRun.Kind.MANUAL)
        with transaction.atomic():
            audit.record(
                actor=request.user,
                action="backup.manual",
                entity="backup_run",
                entity_id=run.pk,
                after={"status": run.status, "seq": run.seq, "path": run.path, "message": run.message},
            )
        return Response(BackupRunSerializer(run).data, status=status.HTTP_201_CREATED)


class BackupRunListView(ListAPIView):
    """«سجل التشغيل»: backup runs, newest first."""

    permission_classes = [IsAuthenticated]
    serializer_class = BackupRunSerializer

    def get_queryset(self):
        return BackupRun.objects.select_related("created_by").prefetch_related("uploads").order_by("-created_at")


class BackupSettingsView(APIView):
    def get_permissions(self):
        return [IsManager()] if self.request.method == "PATCH" else [IsAuthenticated()]

    @extend_schema(responses=BackupSettingsSerializer)
    def get(self, request):
        return Response(BackupSettingsSerializer(export.backup_settings()).data)

    @extend_schema(request=BackupSettingsUpdateSerializer, responses=BackupSettingsSerializer)
    def patch(self, request):
        data = BackupSettingsUpdateSerializer(export.backup_settings(), data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        return Response(BackupSettingsSerializer(services.update_settings(request.user, **data.validated_data)).data)


# --- Owner PC ---------------------------------------------------------------------------------


class ManagerOrFirstImport(BasePermission):
    """Import needs a manager (artboard 6.13 B); the very first import on an empty owner PC has no users yet."""

    def has_permission(self, request, view):
        if not User.objects.exists():
            return True
        return IsManager().has_permission(request, view)


class OwnerStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OwnerStatusSerializer)
    def get(self, request):
        last = merge.last_imported()
        as_of = last.data_as_of if last else None
        public = None
        if keys.identity_path().exists():
            public = str(keys.load().to_public())
        return Response(
            OwnerStatusSerializer(
                {
                    "data_as_of": as_of,
                    "last_import": last,
                    "public_key": public,
                    "hours_old": int((timezone.now() - as_of).total_seconds() // 3600) if as_of else None,
                }
            ).data
        )


def _confirm_unless_first_import(request) -> None:
    """Spec §6.8: importing a backup is a sensitive action (X-Confirm-Token) — except the very first import
    on an empty owner PC, where nobody can sign in yet."""
    if User.objects.exists():
        require_confirmation(request)


class OwnerImportView(APIView):
    """Import a backup file (USB). Runs the five checks; merges only if all pass (artboard 6.13 C)."""

    permission_classes = [ManagerOrFirstImport]
    parser_classes = [MultiPartParser]

    @extend_schema(request=ImportRequestSerializer, responses={201: ImportRunSerializer})
    def post(self, request):
        _confirm_unless_first_import(request)
        data = ImportRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        raw = upload.read()
        merge.save_incoming_file(raw, upload.name)
        actor = request.user if request.user.is_authenticated else None
        result = merge.import_backup(
            actor,
            raw,
            source=ImportRun.Source.FILE,
            file_name=upload.name,
            allow_older=data.validated_data["allow_older"],
        )
        code = (
            status.HTTP_201_CREATED
            if result.run.status == ImportRun.Status.OK
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        return Response(ImportRunSerializer(result.run).data, status=code)


class OwnerImportRunsView(ListAPIView):
    """«سجل الاستيراد»."""

    permission_classes = [IsAuthenticated]
    serializer_class = ImportRunSerializer

    def get_queryset(self):
        return ImportRun.objects.select_related("created_by").order_by("-created_at")


class OwnerBackupView(APIView):
    """The owner PC's own backup of its (imported) data, encrypted to the owner key."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={201: BackupRunSerializer})
    def post(self, request):
        run = export.run_backup(request.user, BackupRun.Kind.MANUAL)
        with transaction.atomic():
            audit.record(
                actor=request.user,
                action="backup.manual",
                entity="backup_run",
                entity_id=run.pk,
                after={"status": run.status, "seq": run.seq, "path": run.path, "message": run.message},
            )
        return Response(BackupRunSerializer(run).data, status=status.HTTP_201_CREATED)


# --- Google Drive (both PCs; the owner PC under owner/) ---------------------------------------------


def _drive_status() -> dict:
    email = None
    token = drive.load_token()
    if token:
        email = token.get("email")
    return {
        "configured": drive.client_secret_path().exists(),
        "linked": token is not None,
        "email": email,
        "pending_uploads": drive.pending_runs().count(),
        "last_upload_at": drive.last_upload_at(),
    }


class DriveStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DriveStatusSerializer)
    def get(self, request):
        return Response(DriveStatusSerializer(_drive_status()).data)


class DriveAuthUrlView(APIView):
    """«ربط حساب» (manager): opens Google's consent page; Google returns to ``…/drive/callback``."""

    permission_classes = [IsManager]
    prefix = "backup"

    @extend_schema(request=None, responses=AuthUrlSerializer)
    def post(self, request):
        return Response({"url": drive.auth_url(self.prefix)})


class DriveCallbackView(APIView):
    """Browser redirect from Google (no session token in the browser); protected by the OAuth state."""

    permission_classes = [AllowAny]
    authentication_classes = []
    prefix = "backup"

    @extend_schema(exclude=True)
    def get(self, request):  # pragma: no cover - needs Google
        email = drive.finish_auth(
            self.prefix, request.query_params.get("code", ""), request.query_params.get("state", "")
        )
        token = drive.load_token()
        token["email"] = email
        drive.save_token(token)
        page = (
            f"<!doctype html><html dir='rtl' lang='ar'><meta charset='utf-8'><body style='font-family:sans-serif'>"
            f"<h2>تم ربط حساب Drive</h2><p dir='ltr'>{email}</p><p>يمكنك إغلاق هذه النافذة.</p></body></html>"
        )
        return HttpResponse(page)


class DriveUnlinkView(APIView):
    """«فصل الحساب» (manager)."""

    permission_classes = [IsManager]

    @extend_schema(request=None, responses=DriveStatusSerializer)
    def post(self, request):
        before = _drive_status()
        drive.unlink_account()
        with transaction.atomic():
            audit.record(
                actor=request.user, action="backup.drive_unlink", entity="drive", before={"email": before.get("email")}
            )
        return Response(DriveStatusSerializer(_drive_status()).data)


class DriveSyncView(APIView):
    """«مزامنة مع Drive»: reception uploads pending backups; the owner PC downloads newer ones."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=SyncResultSerializer)
    def post(self, request):
        if settings.SKYTOWERS_ROLE == "owner":
            fetched = drive.download_new()
            message = f"نُزّلت {len(fetched)} نسخ جديدة" if fetched else "لا جديد على Drive"
            return Response(SyncResultSerializer({"uploaded": 0, "downloaded": fetched, "message": message}).data)
        uploaded = drive.upload_pending(request.user)
        message = f"رُفعت {uploaded} نسخ" if uploaded else "لا جديد — كل النسخ مرفوعة"
        return Response(SyncResultSerializer({"uploaded": uploaded, "downloaded": [], "message": message}).data)


class OwnerDriveAuthUrlView(DriveAuthUrlView):
    prefix = "owner"


class OwnerDriveCallbackView(DriveCallbackView):
    prefix = "owner"


class CandidatesView(APIView):
    """Import dialog step 1 (artboard 6.13 C): files in ``incoming/`` and on Drive, tagged new / imported / older."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CandidateSerializer(many=True))
    def get(self, request):
        last = merge.last_imported()
        newest = last.backup_seq if last and last.backup_seq else 0
        imported = set(ImportRun.objects.filter(status=ImportRun.Status.OK).values_list("backup_seq", flat=True))
        found: dict[str, dict] = {}
        folder = drive.incoming_dir()
        if folder.exists():
            for path in folder.glob("skytowers-*.age"):
                parsed = rules.parse_file_name(path.name)
                if parsed:
                    found[path.name] = {
                        "name": path.name,
                        "seq": parsed[1],
                        "size": path.stat().st_size,
                        "drive_file_id": None,
                        "local": True,
                    }
        if drive.is_linked():
            try:
                for remote in drive.remote_backups(drive.get_client()):
                    entry = found.setdefault(
                        remote.name, {"name": remote.name, "seq": remote.parsed[1], "size": remote.size, "local": False}
                    )
                    entry["drive_file_id"] = remote.id
            except ApiError:
                pass  # offline: show what is on this PC
        rows = []
        for entry in sorted(found.values(), key=lambda e: e["seq"], reverse=True):
            state = "imported" if entry["seq"] in imported else ("new" if entry["seq"] > newest else "older")
            rows.append({**entry, "state": state})
        return Response(CandidateSerializer(rows, many=True).data)


class OwnerImportFromDriveView(APIView):
    """Import a candidate by Drive id or by name in ``incoming/`` (spec §7: import/run with drive_file_id)."""

    permission_classes = [ManagerOrFirstImport]

    @extend_schema(request=DriveImportSerializer, responses={201: ImportRunSerializer})
    def post(self, request):
        _confirm_unless_first_import(request)
        data = DriveImportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v.get("drive_file_id"):
            name, raw = drive.fetch_one(v["drive_file_id"])
            source = ImportRun.Source.DRIVE
        else:
            path = drive.incoming_dir() / Path(v["name"]).name
            if not path.exists():
                raise ApiError("not_found", 404)
            name, raw, source = path.name, path.read_bytes(), ImportRun.Source.FILE
        actor = request.user if request.user.is_authenticated else None
        result = merge.import_backup(actor, raw, source=source, file_name=name, allow_older=v["allow_older"])
        ok = result.run.status == ImportRun.Status.OK
        return Response(
            ImportRunSerializer(result.run).data,
            status=status.HTTP_201_CREATED if ok else status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
