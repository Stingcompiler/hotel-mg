from django.urls import path

from . import views

backup_urls = [
    path("run", views.BackupRunView.as_view(), name="backup-run"),
    path("runs", views.BackupRunListView.as_view(), name="backup-runs"),
    path("settings", views.BackupSettingsView.as_view(), name="backup-settings"),
    path("drive/status", views.DriveStatusView.as_view(), name="backup-drive-status"),
    path("drive/auth-url", views.DriveAuthUrlView.as_view(), name="backup-drive-auth-url"),
    path("drive/callback", views.DriveCallbackView.as_view(), name="backup-drive-callback"),
    path("drive/unlink", views.DriveUnlinkView.as_view(), name="backup-drive-unlink"),
    path("drive/sync", views.DriveSyncView.as_view(), name="backup-drive-sync"),
]

owner_urls = [
    path("status", views.OwnerStatusView.as_view(), name="owner-status"),
    # Local settings of the owner PC (retention, second folder, Drive); the middleware only lets owner/ writes through.
    path("settings", views.BackupSettingsView.as_view(), name="owner-settings"),
    path("import/run", views.OwnerImportView.as_view(), name="owner-import"),
    path("import/runs", views.OwnerImportRunsView.as_view(), name="owner-import-runs"),
    path("backup/run", views.OwnerBackupView.as_view(), name="owner-backup"),
    path("import/candidates", views.CandidatesView.as_view(), name="owner-import-candidates"),
    path("import/drive", views.OwnerImportFromDriveView.as_view(), name="owner-import-drive"),
    path("drive/status", views.DriveStatusView.as_view(), name="owner-drive-status"),
    path("drive/auth-url", views.OwnerDriveAuthUrlView.as_view(), name="owner-drive-auth-url"),
    path("drive/callback", views.OwnerDriveCallbackView.as_view(), name="owner-drive-callback"),
    path("drive/unlink", views.DriveUnlinkView.as_view(), name="owner-drive-unlink"),
    path("drive/sync", views.DriveSyncView.as_view(), name="owner-drive-sync"),
]
