from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsManager

from . import export, keys, merge, services
from .models import BackupRun, ImportRun
from .serializers import (
    BackupRunSerializer,
    BackupSettingsSerializer,
    BackupSettingsUpdateSerializer,
    ImportRequestSerializer,
    ImportRunSerializer,
    OwnerStatusSerializer,
)


class BackupRunView(APIView):
    """«نسخة احتياطية الآن» (artboard 6.13): writes the encrypted file now; the result line shows it."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={201: BackupRunSerializer})
    def post(self, request):
        run = export.run_backup(request.user, BackupRun.Kind.MANUAL)
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


class OwnerImportView(APIView):
    """Import a backup file (USB). Runs the five checks; merges only if all pass (artboard 6.13 C)."""

    permission_classes = [ManagerOrFirstImport]
    parser_classes = [MultiPartParser]

    @extend_schema(request=ImportRequestSerializer, responses={201: ImportRunSerializer})
    def post(self, request):
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
        return Response(BackupRunSerializer(run).data, status=status.HTTP_201_CREATED)
