from __future__ import annotations
from concurrent import futures
import itertools
from typing import Iterable

from flask import current_app as app, request

from library.api import api_base, api_path
from backend.common import assembly_data, setup, evaluate


class AssemblyMirrorCandidate:
    """Represents a candidate for assembly mirror.

    Attributes:
        mate_connectors: A dict mapping mate_ids to a boolean which is True if the mate connector is used and False otherwise.
        fully_used: True if all mate connectors are used.
    """

    def __init__(
        self,
        instance: dict,
        assembly: assembly_data.Assembly,
        assembly_features: assembly_data.AssemblyFeatures,
    ) -> None:
        """ """
        self.instance = instance
        self.part = assembly.get_part_from_instance(instance)
        self.part_path = assembly.resolve_part_path(instance)
        self.element_path = self.part_path.path
        self.mate_connectors = self._init_mate_connectors(assembly_features)
        self.all_used = all(self.mate_connectors.values())

    def _init_mate_connectors(
        self, assembly_features: assembly_data.AssemblyFeatures
    ) -> dict[str, bool]:
        return dict(
            (
                mate_connector,
                assembly_features.is_mate_connector_used(self.instance, mate_connector),
            )
            for mate_connector in self.part.get("mateConnectors", [])
        )


class AssemblyMirror:
    """Represents the execution of a single assembly mirror operation."""

    def __init__(self, api: api_base.Api, assembly_path: api_path.ElementPath) -> None:
        self.api = api
        self.path = assembly_path

    def execute(self) -> None:
        self._init_assemblies()
        candidates = self._get_candidates()
        part_studios = self._collect_part_studios(candidates)
        evaluate_result = evaluate.evaluate_assembly_mirror_parts(
            self.api, part_studios
        )

        # create_assembly_mirror_parts(
        #     candidates, evaluate_result
        # )

    def _init_assemblies(self) -> None:
        with futures.ThreadPoolExecutor(2) as executor:
            assembly_future = executor.submit(
                assembly_data.assembly, self.api, self.path
            )
            assembly_features_future = executor.submit(
                assembly_data.assembly_features, self.api, self.path
            )
        self.assembly: assembly_data.Assembly = assembly_future.result()
        self.assembly_features: assembly_data.AssemblyFeatures = (
            assembly_features_future.result()
        )

    def _make_candidate(self, instance: dict) -> AssemblyMirrorCandidate:
        return AssemblyMirrorCandidate(instance, self.assembly, self.assembly_features)
        # part = self.assembly.get_part_from_instance(instance)
        # part_path = self.assembly.resolve_part_path(instance)
        # return AssemblyMirrorCandidate(
        #     instance, part, part_path, self._make_mate_connectors(instance, part)
        # )

    def _get_candidates(self) -> list[AssemblyMirrorCandidate]:
        """Collects a list of candidates which can potentially be mirrored."""
        return [
            self._make_candidate(instance)
            for instance in self.assembly.get_instances()
            if instance.get("type") == "Part"
        ]

    def _collect_part_studios(
        self, candidates: Iterable[AssemblyMirrorCandidate]
    ) -> Iterable[api_path.ElementPath]:
        """Maps candidates into a set of unique part studios.

        Candidates without any unused mate connectors are first filtered out.
        """
        return set(
            candidate.element_path for candidate in candidates if not candidate.all_used
        )

    def _has_used_origin_mate(
        self, candidate: AssemblyMirrorCandidate, origin_base_mates: set[str]
    ) -> bool:
        """Returns True if the candidate has a used origin base mate."""
        intersections = origin_base_mates.intersection(candidate.mate_connectors)
        return any(
            candidate.mate_connectors[intersection] for intersection in intersections
        )

    def _collect_used_origin_paths(
        self,
        candidates: Iterable[AssemblyMirrorCandidate],
        origin_base_mates: set[str],
    ) -> set[api_path.PartPath]:
        """Returns a set of part_paths representing parts which are ineligible for origin mirroring."""
        return set(
            candidate.part_path
            for candidate in candidates
            if self._has_used_origin_mate(candidate, origin_base_mates)
        )

    def _elibible_for_standard_mirror(
        self, candidate: AssemblyMirrorCandidate, base_to_target_mates: dict[str, str]
    ) -> bool:
        """Returns True if the candidate is eligible for assembly mirror.

        Formally, this means the candidate has two unused mates matching a key-value pair in base_to_target_mates.
        """
        # standard_mate_intersection = set(
        #     itertools.chain(evaluate_result.base_to_target_mates.items())
        # ).intersection(mate_ids)
        # if len(standard_mate_intersection) == 2:
        #     # Handle mirror mate
        #     continue
        return True

    def _create_assembly_mirror_parts(
        self,
        candidates: list[AssemblyMirrorCandidate],
        evaluate_result: evaluate.AssemblyMirrorEvaluateData,
    ) -> list[dict]:
        """Forms the list of assembly mirror candidates into a list of AssemblyMirrorParts to be assembled.

        Notably, candidates are first trimmed according to the following logic:
        1. For an origin candidate, the instance is trimmed if there already exists some other instance of the part in the assembly
        which is fastened to the origin.
        2. For a regular candidate, the instance is trimmed if either mate is already used (which handles both base and mirrored instances).
        """

        # Trim instance_paths based on parts_to_mates_dict and the dict returned by evaluate
        # More specifically:
        # For each instance in instance_paths:
        # Iterate over the mate ids in evalute_result.
        # If necessary, trim the candidate.
        # Otherwise, construct the mate and add it.
        used_origin_paths = self._collect_used_origin_paths(
            candidates, evaluate_result.origin_base_mates
        )

        for candidate in candidates:
            # part_path = assembly.resolve_part_path(instance)
            # mate_ids: list[str] = parts_to_mate_ids.get(part_path, [])
            if candidate.part_path not in used_origin_paths:
                origin_mate_intersection = (
                    evaluate_result.origin_base_mates.intersection(
                        candidate.mate_connectors.keys()
                    )
                )
                if len(origin_mate_intersection) >= 1:
                    # Handle origin mate
                    continue
            elif self._elibible_for_standard_mirror(
                candidate, evaluate_result.base_to_target_mates
            ):
                pass

            # standard_mate_intersection = set(
            #     itertools.chain(evaluate_result.base_to_target_mates.items())
            # ).intersection(mate_ids)
            # if len(standard_mate_intersection) == 2:
            #     # Handle mirror mate
            #     continue

        return []


def execute():
    api = setup.create_api(request, logging=False)
    if api == None:
        return {"error": "An onshape oauth token is required."}

    body = request.get_json()
    if body == None:
        return {"error": "A request body is required."}
    assembly_path = api_path.make_element_path_from_obj(body)

    AssemblyMirror(api, assembly_path).execute()

    return {"message": "Success"}
