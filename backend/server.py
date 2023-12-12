import flask
import os
from library.api.endpoints import documents

from backend.endpoints import auto_assembly, generate_assembly, update_references
from backend.common import setup

app = flask.Flask(__name__)


@app.errorhandler(setup.ApiException)
def api_exception(e: setup.ApiException):
    return e.to_dict(), e.status_code


@app.route("<path:element_path>auto-assembly", methods=["POST"])
def auto_assembly_route():
    return auto_assembly.execute()


@app.route("<path:element_path>/generate-assembly", methods=["POST"])
def generate_assembly_route():
    return generate_assembly.execute()


@app.route("<path:document_path>/update-references", methods=["POST"])
def update_references_route():
    """Updates references in a document.

    Args:
        fromDocumentIds: A list of documentIds to look for when deciding what to update.
        If included, only references to the specified documents will be updated.
        Otherwise, all outdated references will be updated.
    Returns:
        updates: The number of references which were updated.
    """
    return update_references.execute()


@app.route("<path:document_path>/create-version", methods=["POST"])
def create_version_route():
    """Creates a version.

    Returns the id of the created version.
    """
    api = setup.get_api()
    document_path = setup.get_document_path()
    result = documents.make_version(
        api, document_path, setup.get_value("name"), setup.get_value("description")
    )
    return {"id": result["id"]}


@app.route("<path:document_path>/next-version-name", methods=["GET"])
def next_version_name_route():
    """Returns the next default version name for a given document."""
    api = setup.get_api()
    document_path = setup.get_document_path()
    versions = documents.get_versions(api, document_path)
    # len(versions) is correct due to Start version
    return {"name": "V{}".format(len(versions))}


if __name__ == "__main__":
    app.run(
        debug=True,
        port=int(os.environ.get("PORT", 8080)),
    )
