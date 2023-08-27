from __future__ import annotations
from typing import Self
from library.api import api_path, api_base
from library.api.endpoints import assemblies


class AssemblyData:
    """Contains information from Onshape about an assembly."""

    def __init__(self, assembly_data: dict, path: api_path.ElementPath) -> None:
        self.assembly_data = assembly_data
        self.path = path

    def get_parts(self) -> dict:
        return self.assembly_data["parts"]
        # result = self.assembly_data.get("parts", None)
        # if not result:
        #     raise RuntimeError("Unexpected response from Onshape.")
        # return result

    def get_instances(self) -> list[dict]:
        return self.assembly_data["rootAssembly"]["instances"]

    def extract_part_studios(self) -> set[api_path.ElementPath]:
        """Constructs a set of unique part studio paths in the assembly."""
        return set(self.make_path(part) for part in self.get_parts())

    def get_parts_to_mates_dict(self) -> dict[api_path.PartPath, list[str]]:
        """Constructs a dict which maps part paths to the unique mate ids owned by each part."""

        result = {}
        for part in self.get_parts():
            part_path = api_path.PartPath(self.make_path(part), part["partId"])
            for mate_connector in part.get("mateConnectors", []):
                mate_id = mate_connector["featureId"]
                values = result.get(part_path, [])
                values.append(mate_id)
                result[part_path] = values
        return result

    def make_path(self, part: dict) -> api_path.ElementPath:
        """Constructs a path to an instance or a part.

        Arg:
            part: An instance or part in an assembly.
        """
        if "documentVersion" in part:
            return api_path.ElementPath(
                api_path.DocumentPath(part["documentId"], part["documentVersion"], "v"),
                part["elementId"],
            )
        return api_path.ElementPath(
            api_path.DocumentPath(part["documentId"], self.path.path.workspace_id, "w"),
            part["elementId"],
        )


def assembly_data(
    api: api_base.Api, assembly_path: api_path.ElementPath
) -> AssemblyData:
    assembly_data = assemblies.get_assembly(
        api, assembly_path, include_mate_features=True, include_mate_connectors=True
    )
    return AssemblyData(assembly_data, assembly_path)
