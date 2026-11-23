from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

urlpatterns = [
    # Old flat progress admin (T4.1) is now grouped per joiner (T6.2); keep bookmarks working.
    # ponytail: everything lands on the joiner list, not the matching joiner — one redirect, no lookup.
    re_path(
        r"^admin/core/joinerprogress/",
        RedirectView.as_view(pattern_name="admin:core_joiner_changelist", permanent=True),
    ),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]
