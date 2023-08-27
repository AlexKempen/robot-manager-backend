from concurrent import futures
import pathlib
import dataclasses
from typing import Callable, Iterable

from flask import current_app as app, request

from library.api import api_base, api_path
from library.api.endpoints import (
    assemblies,
    assembly_features,
    part_studios,
)

SCRIPT_PATH = pathlib.Path("backend/scripts")


def execute():
    pass
