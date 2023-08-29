from concurrent import futures
from typing import Callable, Iterable

from flask import current_app as app, request

from library.api import api_base, api_path
from library.api.endpoints import (
    assemblies,
    assembly_features,
)
from backend.common import assembly_data, setup, evaluate


def execute():
    api = setup.create_api(request, logging=False)
    if api == None:
        return {"error": "An onshape oauth token is required."}

    body = request.get_json()
    if body == None:
        return {"error": "A request body is required."}
    assembly_path = api_path.make_element_path_from_obj(body)

    with futures.ThreadPoolExecutor(2) as executor:
        assembly_future = executor.submit(
            assembly_data.assembly,
            api,
            assembly_path,
        )
        assembly_features_future = executor.submit(
            assembly_data.assembly_features, api, assembly_path
        )

    assembly: assembly_data.Assembly = assembly_future.result()
    assembly_features: assembly_data.AssemblyFeatures = (
        assembly_features_future.result()
    )

    # part_studio_paths = assembly.extract_unique_part_studios()
    instance_paths = get_assembly_mirror_candidates(assembly, assembly_features)
    part_studios = collect_part_studios(instance_paths)
    evaluate_result = evaluate.evaluate_assembly_mirror_parts(api, part_studios)

    # wait to resolve assembly features

    return {"message": "Success"}


def get_assembly_mirror_candidates(
    assembly: assembly_data.Assembly, assembly_features: assembly_data.AssemblyFeatures
) -> Iterable[api_path.PartPath]:
    """Collects a list of all part paths representing parts which can potentially be mirrored.

    In particular, this function filters out all parts which don't have any unused mate connectors.
    Returns a list of part paths, one for each candidate instance.

    This list may be further trimmed once the parts are instantiated.
    """
    instances = assembly.get_instances().copy()
    instances = filter(lambda instance: instance["type"] == "Part", instances)

    def has_unused_mate_connectors(instance: dict) -> bool:
        part = assembly.get_part_from_instance(instance)
        if "mateConnectors" not in part:
            return False
        for mate_connector in part["mateConnectors"]:
            if assembly_features.is_mate_connector_used(instance, mate_connector):
                return True
        return False

    instances = filter(has_unused_mate_connectors, instances)
    return [
        api_path.PartPath(assembly.resolve_path(instance), instance["partId"])
        for instance in instances
    ]


def collect_part_studios(
    instance_paths: Iterable[api_path.PartPath],
) -> Iterable[api_path.ElementPath]:
    """Maps part paths into a set of unique part studios."""
    return set(instance_path.path for instance_path in instance_paths)


# evaluate part studios


def trim_candidates(
    instance_paths: Iterable[api_path.PartPath],
    assembly: assembly_data.Assembly,
) -> list[api_path.PartPath]:
    """Trims the list of assembly mirror candidates based on the data returned by evalute part studio.

    In particular, removes each instance which doesn't have the appropriate mate ids.
    """
    parts_to_mate_ids = assembly.get_parts_to_mate_ids()

    # Trim instance_paths based on parts_to_mates_dict and the dict returned by evaluate
    # For each instance in instance_paths:
    # Iterate over the matches in the corresponding part studio in evalute_result.
    # If the base_mate_id belongs to the instance, keep it
    # Otherwise trim the candidate
    return []


class AssemblyMirrorPart:
    """Represents a part which assembly mirror will be performed on."""

    def __init__(self) -> None:
        pass


class OriginPart(AssemblyMirrorPart):
    """Represents an assembly mirror part which shall be constrained to the origin."""

    pass


class MirrorPart(AssemblyMirrorPart):
    """Represents an assembly mirror part which shall be constrained to the original instance."""

    pass
