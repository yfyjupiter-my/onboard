from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import translation
from django.utils.cache import patch_vary_headers

ADMIN_PREFIX = "/admin/"  # matches path("admin/", ...) in onboard/urls.py; compared with path_info (no /vn)
# T7.3: derived from the instance's session cookie: "admin_sessionid" for Malaysia (unchanged),
# "admin_sessionid_vn" for /vn/, so instances sharing the domain never read each other's admin session.
ADMIN_SESSION_COOKIE = f"admin_{settings.SESSION_COOKIE_NAME}"
ADMIN_COOKIE_PATH = (getattr(settings, "FORCE_SCRIPT_NAME", None) or "") + ADMIN_PREFIX


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
            morsel["path"] = ADMIN_COOKIE_PATH
            response.cookies[ADMIN_SESSION_COOKIE] = morsel
        elif morsel is not None:
            response.cookies[settings.SESSION_COOKIE_NAME] = morsel
        return response


class InstanceLocaleMiddleware:
    """T7.1: serve the instance's LANGUAGE_CODE unless the user picked another of LANGUAGES
    with the toggle (Django's language cookie, set by the set_language POST).

    /admin/ is always English. Unlike LocaleMiddleware this ignores Accept-Language: a Vietnamese joiner on an English
    browser still gets Vietnamese first, which is the point of a per-country instance.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if request.path_info.startswith(ADMIN_PREFIX):
            # HR/IT admin stays English: its own labels, help text and validation are English,
            # so a translated Django chrome around them would be a half-and-half page.
            lang = "en"
        elif lang not in dict(settings.LANGUAGES):  # unknown/forged value → instance default
            lang = settings.LANGUAGE_CODE
        translation.activate(lang)
        request.LANGUAGE_CODE = translation.get_language()
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", request.LANGUAGE_CODE)
        patch_vary_headers(response, ("Cookie",))
        return response
