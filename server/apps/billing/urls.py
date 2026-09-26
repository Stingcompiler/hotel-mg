from django.urls import path

from . import views

folio_urls = [
    path("<uuid:pk>", views.FolioDetailView.as_view(), name="folio-detail"),
    path("<uuid:pk>/lines", views.FolioLineView.as_view(), name="folio-lines"),
    path("<uuid:pk>/lines/<uuid:line_pk>/reverse", views.ReverseLineView.as_view(), name="folio-line-reverse"),
    path("<uuid:pk>/payments", views.PaymentCreateView.as_view(), name="folio-payments"),
    path("<uuid:pk>/refunds", views.RefundView.as_view(), name="folio-refunds"),
]

payment_urls = [
    path("<uuid:pk>", views.PaymentDetailView.as_view(), name="payment-detail"),
    path("<uuid:pk>/reverse", views.ReversePaymentView.as_view(), name="payment-reverse"),
]
