from flask import current_app as app, request

from library.api import api_path
from backend.common import setup


def execute():
    api = setup.create_api(request, logging=False)
    if api == None:
        return {"error": "An onshape oauth token is required."}

    body = request.get_json()
    if body == None:
        return {"error": "A request body is required."}
    assembly_path = api_path.make_element_path_from_obj(body)

    return {"message": "Success"}
