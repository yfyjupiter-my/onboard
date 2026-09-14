from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware

ADMIN_PREFIX = "/admin/"  # matches path("admin/", ...) in onboard/urls.py
ADMIN_SESSION_COOKIE = "admin_sessionid"


class SplitSessionMiddleware(SessionMiddleware):
    """T6.6: /admin/ and the joiner frontend get separate session cookies, so signing in
    (or out) on one side never signs in (or out) the other.

    ponytail: swaps the cookie around Django's own SessionMiddleware instead of copying it,
    so expiry/save/delete logic stays Django's.
    """

    def process_request(self, request):
        if request.path_info.startswith(ADMIN_PREFIX):
            cookies = dict(request.COOKIES)
            # Never let the frontend cookie (path "/") authenticate an admin request.
            cookies.pop(settings.SESSION_COOKIE_NAME, None)
            if ADMIN_SESSION_COOKIE in cookies:
                cookies[settings.SESSION_COOKIE_NAME] = cookies[ADMIN_SESSION_COOKIE]
            request.COOKIES = cookies
        super().process_request(request)

    def process_response(self, request, response):
        response = super().process_response(request, response)
        morsel = response.cookies.pop(settings.SESSION_COOKIE_NAME, None)
        if morsel is not None and request.path_info.startswith(ADMIN_PREFIX):
            morsel.set(ADMIN_SESSION_COOKIE, morsel.value, morsel.coded_value)
            morsel["path"] = ADMIN_PREFIX
            response.cookies[ADMIN_SESSION_COOKIE] = morsel
        elif morsel is not None:
            response.cookies[settings.SESSION_COOKIE_NAME] = morsel
        return response
