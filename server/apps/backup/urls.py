from django.urls import path

from . import views

backup_urls = [
    path("run", views.BackupRunView.as_view(), name="backup-run"),
    path("runs", views.BackupRunListView.as_view(), name="backup-runs"),
    path("settings", views.BackupSettingsView.as_view(), name="backup-settings"),
]

owner_urls = [
    path("status", views.OwnerStatusView.as_view(), name="owner-status"),
    path("import/run", views.OwnerImportView.as_view(), name="owner-import"),
    path("import/runs", views.OwnerImportRunsView.as_view(), name="owner-import-runs"),
    path("backup/run", views.OwnerBackupView.as_view(), name="owner-backup"),
]
