from django.urls import path

from . import views

urlpatterns = [
    path("board", views.BoardView.as_view(), name="followup-board"),
    path("tasks", views.TaskListView.as_view(), name="followup-tasks"),
    path("tasks/<uuid:pk>", views.TaskDetailView.as_view(), name="followup-task"),
    path("tasks/<uuid:pk>/actions", views.TaskActionView.as_view(), name="followup-task-action"),
    path("toasts", views.ToastsView.as_view(), name="followup-toasts"),
    path("rules", views.RuleListView.as_view(), name="followup-rules"),
    path("rules/preview", views.RulePreviewView.as_view(), name="followup-rule-preview"),
    path("rules/<uuid:pk>", views.RuleDetailView.as_view(), name="followup-rule"),
]
