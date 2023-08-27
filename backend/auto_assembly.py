from concurrent import futures
import pathlib
import dataclasses
from typing import Callable, Iterable

from flask import current_app as app, request

from library.api import api_base, api_path
from library.api.endpoints import (
    assemblies,
    assembly_features,
)
from backend.common import assembly_data, setup, evaluate


SCRIPT_PATH = pathlib.Path("backend/scripts")


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
            assembly_data.assembly_data,
            api,
            assembly_path,
        )
        assembly_features_future = executor.submit(
            assemblies.get_assembly_features, api, assembly_path
        )

    assembly = assembly_future.result()

    part_studio_paths = assembly.extract_part_studios()
    parts_to_mates_dict = assembly.get_parts_to_mates_dict()

    part_maps = evaluate.evalute_part_studios(api, part_studio_paths)
    targets_to_mate_connectors = evaluate.evaluate_targets(
        api, part_maps.mates_to_targets
    )

    # wait to resolve assembly features
    assembly_features = assembly_features_future.result()
    instances_to_mates = get_instances_to_mates(
        assembly, assembly_features, parts_to_mates_dict
    )
    count = iterate_mate_ids(
        api,
        assembly_path,
        instances_to_mates,
        try_add_instance,
        part_maps,
        targets_to_mate_connectors,
    )
    updated_assembly = assembly_data.AssemblyData(
        assemblies.get_assembly(api, assembly_path, include_mate_connectors=True),
        assembly_path,
    )
    updated_instances = updated_assembly.get_instances()
    # reverse instances to collect new ones
    new_instances = updated_instances[-count:]
    iterate_mate_ids(
        api,
        assembly_path,
        instances_to_mates,
        add_mate,
        part_maps,
        targets_to_mate_connectors,
        new_instances,
    )

    return {"message": "Success"}


def get_instances_to_mates(
    assembly: assembly_data.AssemblyData,
    assembly_features: dict,
    parts_to_mates: dict[api_path.PartPath, list[str]],
) -> list[tuple[dict, str]]:
    """Returns a list of tuples representing each instance-mate id pair."""

    result = []
    for instance in assembly.get_instances():
        mate_ids = get_part_mate_ids(instance, assembly, parts_to_mates)
        for mate_id in mate_ids:
            if is_mate_unused(instance, mate_id, assembly_features):
                result.append((instance, mate_id))
    return result


def is_mate_unused(instance: dict, mate_id: str, assembly_features: dict) -> bool:
    """Returns true if the specified mate connector on the given part_path isn't used in any mate features.

    Procedure:
        Iterate over features.
        For each fastened mate, iterate over its queries. For each mate connector query, if its feature id equals our mate_id, the mate is used.

    Note this procedure isn't very performant since assembly_features is iterated over many times (and each iteration is also slow).
    Speed could be improved by first collecting all mate_ids and then using the above technique alongside a set of all mate ids.
    """
    for feature in assembly_features["features"]:
        if is_fastened_mate(feature):
            queries = get_query_parameter(feature)
            if any(
                query["featureId"] == mate_id and query["path"][0] == instance["id"]
                for query in queries
            ):
                return False
    return True


def is_fastened_mate(feature: dict) -> bool:
    """Returns true if feature is a fastened mate."""
    if feature.get("featureType", None) != "mate":
        return False
    for parameter in feature["parameters"]:
        if parameter["parameterId"] == "mateType":
            if parameter["value"] != "FASTENED":
                return False
            else:
                break
    return True


def get_query_parameter(feature: dict) -> list[dict]:
    for parameter in feature["parameters"]:
        if parameter["parameterId"] == "mateConnectorsQuery":
            return parameter["queries"]
    return []


def get_part_mate_ids(
    instance: dict,
    assembly: assembly_data.AssemblyData,
    part_to_mates: dict[api_path.PartPath, list[str]],
) -> list[str]:
    """Fetches the mate ids of an instance.

    Returns a list of the mate ids on the instance.
    Returns [] if the instance isn't a valid part or doesn't have any mates.
    """
    if instance["type"] != "Part":
        return []
    part_path = api_path.PartPath(assembly.make_path(instance), instance["partId"])
    return part_to_mates.get(part_path, [])


def iterate_mate_ids(
    api: api_base.Api,
    assembly_path: api_path.ElementPath,
    instances_to_mates: Iterable[tuple[dict, str]],
    fn: Callable[..., futures.Future | None],
    *args
) -> int:
    """Iterates over instances_to_mates, calling fn on each.

    Args:
        fn: A function taking an executor, an api, an assembly_path, an instance, a mate id, and *args (in that order),
          and which returns a Future or None.

    Returns the number of created threads.
    """
    with futures.ThreadPoolExecutor() as executor:
        threads = []
        for instance, mate_id in instances_to_mates:
            thread = fn(executor, api, assembly_path, instance, mate_id, *args)
            if thread is not None:
                threads.append(thread)

    return len(threads)


def try_add_instance(
    executor: futures.ThreadPoolExecutor,
    api: api_base.Api,
    assembly: assembly_data.AssemblyData,
    instance: dict,
    mate_id: str,
    part_maps: evaluate.PartMaps,
    targets_to_mate_connectors: dict[str, str],
) -> futures.Future | None:
    if mate_id in part_maps.mates_to_targets and mate_id in targets_to_mate_connectors:
        return executor.submit(
            assemblies.add_parts_to_assembly,
            api,
            assembly.path,
            part_maps.mates_to_targets[mate_id],
        )
    elif mate_id in part_maps.mirror_mates or mate_id in part_maps.origin_mirror_mates:
        part_studio_path = assembly.make_path(instance)
        return executor.submit(
            assemblies.add_parts_to_assembly,
            api,
            assembly.path,
            part_studio_path,
            instance["partId"],
        )
    return None


def add_mate(
    executor: futures.ThreadPoolExecutor,
    api: api_base.Api,
    assembly: assembly_data.AssemblyData,
    instance: dict,
    mate_id: str,
    part_maps: evaluate.PartMaps,
    targets_to_mate_connectors: dict[str, str],
    new_instances: list[dict],
) -> futures.Future | None:
    if mate_id in part_maps.mates_to_targets and mate_id in targets_to_mate_connectors:
        target_path = part_maps.mates_to_targets[mate_id]
        target_mate_connector = targets_to_mate_connectors[mate_id]
        new_instance = find_new_instance(new_instances, assembly, target_path)
        queries = (
            assembly_features.part_studio_mate_connector_query(
                new_instance["id"], target_mate_connector
            ),
            assembly_features.part_studio_mate_connector_query(instance["id"], mate_id),
        )
        feature = assembly_features.fasten_mate("Fasten mate", queries)
        return executor.submit(assemblies.add_feature, api, assembly.path, feature)
    elif mate_id in part_maps.mirror_mates:
        start_mate_id = part_maps.mirror_mates[mate_id]
        target_path = assembly.make_path(instance)
        new_instance = find_new_instance(new_instances, assembly, target_path)
        queries = (
            assembly_features.part_studio_mate_connector_query(
                new_instance["id"], start_mate_id
            ),
            assembly_features.part_studio_mate_connector_query(instance["id"], mate_id),
        )
        feature = assembly_features.fasten_mate("Mirror mate", queries)
    elif mate_id in part_maps.origin_mirror_mates:
        queries = ({}, {})
        feature = assembly_features.fasten_mate("Mirror mate", queries)
    else:
        return None

    return executor.submit(assemblies.add_feature, api, assembly.path, feature)


def find_new_instance(
    new_instances: list[dict],
    assembly: assembly_data.AssemblyData,
    target_path: api_path.ElementPath,
) -> dict:
    for i, new_instance in enumerate(new_instances):
        new_path = assembly.make_path(new_instance)
        if new_path == target_path:
            return new_instances.pop(i)
    raise ValueError("Failed to find added instance.")
