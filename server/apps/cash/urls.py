from django.urls import path

from . import views

shift_urls = [
    path("", views.ShiftHistoryView.as_view(), name="shift-list"),
    path("current", views.CurrentShiftView.as_view(), name="shift-current"),
    path("open", views.OpenShiftView.as_view(), name="shift-open"),
    path("close", views.CloseShiftView.as_view(), name="shift-close"),
    path("<uuid:pk>", views.ShiftDetailView.as_view(), name="shift-detail"),
]

expense_urls = [
    path("", views.ExpenseListView.as_view(), name="expense-list"),
    path("summary", views.ExpenseSummaryView.as_view(), name="expense-summary"),
    path("<uuid:pk>/reverse", views.ReverseExpenseView.as_view(), name="expense-reverse"),
    path("<uuid:pk>/attachments", views.ExpenseAttachmentView.as_view(), name="expense-attachments"),
    path("<uuid:pk>/attachments/<uuid:att_pk>", views.ExpenseAttachmentFileView.as_view(), name="expense-attachment"),
]
