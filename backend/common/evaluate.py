""""Utilities for evaluating FeatureScripts against part studios."""


from concurrent import futures
import dataclasses
import pathlib
from library.api import api_base, api_path
from library.api.endpoints import part_studios

SCRIPT_PATH = pathlib.Path("../scripts")


@dataclasses.dataclass
class PartMaps:
    mates_to_targets: dict[str, api_path.ElementPath] = dataclasses.field(
        default_factory=dict
    )
    mirror_mates: dict[str, str] = dataclasses.field(default_factory=dict)
    origin_mirror_mates: set[str] = dataclasses.field(default_factory=set)


def evalute_part_studios(
    api: api_base.Api, part_studio_paths: set[api_path.ElementPath]
):
    with futures.ThreadPoolExecutor() as executor:
        threads = [
            executor.submit(evalute_part, api, part_studio_path)
            for part_studio_path in part_studio_paths
        ]

        part_maps = PartMaps()
        for future in futures.as_completed(threads):
            result = future.result()
            if not result["valid"]:
                continue

            for values in result["mates"]:
                part_maps.mates_to_targets[
                    values["mateId"]
                ] = api_path.make_element_path_from_obj(values)

            for values in result["mirrors"]:
                if values["mateToOrigin"]:
                    part_maps.origin_mirror_mates.add(values["endMateId"])
                else:
                    part_maps.mirror_mates[values["endMateId"]] = values["startMateId"]

        return part_maps


def evalute_part(api: api_base.Api, part_studio_path: api_path.ElementPath) -> dict:
    with (SCRIPT_PATH / pathlib.Path("parseBase.fs")).open() as file:
        return part_studios.evaluate_feature_script(api, part_studio_path, file.read())


def evaluate_targets(
    api: api_base.Api, mates_to_targets: dict[str, api_path.ElementPath]
) -> dict[str, str]:
    """TODO: Deduplicate target part studios."""
    with futures.ThreadPoolExecutor() as executor:
        threads = {
            executor.submit(evalute_target, api, part_studio_path): target_mate_id
            for target_mate_id, part_studio_path in mates_to_targets.items()
        }

        targets_to_mate_connectors = {}
        for future in futures.as_completed(threads):
            result = future.result()
            target_mate_id = threads[future]
            targets_to_mate_connectors[target_mate_id] = result["targetMateId"]
        return targets_to_mate_connectors


def evalute_target(api: api_base.Api, assembly_path: api_path.ElementPath) -> dict:
    with (SCRIPT_PATH / pathlib.Path("parseTarget.fs")).open() as file:
        return part_studios.evaluate_feature_script(api, assembly_path, file.read())
