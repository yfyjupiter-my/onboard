from .models import JoinerProgress, Material


def topbar_progress(request):
    """T6.7: "3 of 5 complete" + rail fill on every joiner page's top bar.
    Staff/anonymous (admin, login) skip the queries entirely."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.is_staff:
        return {}
    total = Material.objects.filter(is_active=True).count()
    done = JoinerProgress.objects.filter(
        user=user, status=JoinerProgress.COMPLETED, material__is_active=True
    ).count()
    return {"topbar": {"done": done, "total": total, "ratio": done / total if total else 0}}
