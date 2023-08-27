import flask
from library.api import api_base


def extract_token(auth: str) -> str:
    return auth.removeprefix("Basic").strip()


def create_api(request: flask.Request, logging=False) -> api_base.Api | None:
    auth = request.headers.get("Authentication", None)
    if auth == None:
        return None
    return api_base.ApiToken(extract_token(auth), logging=logging)
