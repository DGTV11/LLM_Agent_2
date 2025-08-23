import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from types import ModuleType
from typing import Any, Dict, List, Tuple

import yaml

import db

# from function_node import FunctionNode


def import_from_path(
    module_name: str, file_path: str
) -> (
    ModuleType
):  # * https://docs.python.org/3/library/importlib.html#importing-a-source-file-directly
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec
    assert getattr(spec, "loader", None) and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class FunctionSets:
    agent_id: str

    @property
    def optional_function_set_names(self) -> List[str]:
        return json.loads(
            db.sqlite_db_read_query(
                "SELECT optional_function_sets FROM agents WHERE id = ?;",
                (self.agent_id,),
            )[0][0]
        )

    # def get_function_nodes(self) -> Dict[str, "FunctionNode"]:
    def get_function_nodes(self) -> Dict[str, Any]:
        function_node_list = []

        # *Load nodes

        base_function_sets_dir = os.path.join(
            os.path.dirname(__file__), "function_sets", "base"
        )

        for function_set_file in os.listdir(base_function_sets_dir):
            if not function_set_file.endswith(".py"):
                continue
            function_set_module = import_from_path(
                function_set_file.replace(".py", ""),
                os.path.join(base_function_sets_dir, function_set_file),
            )
            current_set_function_nodes = getattr(
                function_set_module, "FUNCTION_NODES", None
            )
            assert current_set_function_nodes
            assert isinstance(current_set_function_nodes, list)
            function_node_list.extend(current_set_function_nodes)

        optional_function_sets_dir = os.path.join(
            os.path.dirname(__file__), "function_sets", "optional"
        )

        for function_set_name in self.optional_function_set_names:
            function_set_module = import_from_path(
                function_set_name,
                os.path.join(optional_function_sets_dir, function_set_name + ".py"),
            )
            current_set_function_nodes = getattr(
                function_set_module, "FUNCTION_NODES", None
            )
            assert current_set_function_nodes
            assert isinstance(current_set_function_nodes, list)
            function_node_list.extend(current_set_function_nodes)

        # *Convert to dict
        function_node_dict = {
            name: node for name, node in map(lambda n: (n.name, n), function_node_list)
        }

        return function_node_dict

    def __repr__(self) -> str:
        return "\n\n".join(
            [
                yaml.dump(
                    dict(reversed(node.validator.model_json_schema().items())),
                    sort_keys=False,
                ).strip()
                for node in self.get_function_nodes().values()
            ]
        )
