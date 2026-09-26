from django.urls import path

from . import views

report_urls = [
    path("", views.ReportIndexView.as_view(), name="report-index"),
    path("owner-dashboard", views.OwnerDashboardView.as_view(), name="owner-dashboard"),
    path("<slug:name>", views.ReportView.as_view(), name="report"),
    path("<slug:name>/export", views.ReportExportView.as_view(), name="report-export"),
]

# Print data lives next to the resource it prints.
document_urls = [
    path("folios/<uuid:pk>/invoice", views.InvoiceView.as_view(), name="folio-invoice"),
    path("payments/<uuid:pk>/receipt", views.PaymentReceiptView.as_view(), name="payment-receipt"),
    path("expenses/<uuid:pk>/receipt", views.ExpenseReceiptView.as_view(), name="expense-receipt"),
    path("shifts/<uuid:pk>/statement", views.ShiftStatementView.as_view(), name="shift-statement"),
]
