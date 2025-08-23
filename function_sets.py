import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from multiprocessing.connection import Connection
from types import ModuleType
from typing import Any, Dict, List, Tuple

from pocketflow import BaseNode, Node
from pydantic import BaseModel

import db
from memory import FunctionResultContent, Memory, Message


class FunctionNodeMeta(type):
    def __new__(cls, name, bases, namespace):
        if "name" not in namespace:
            raise TypeError(f"Class {name} must define class variable 'name'")
        if not isinstance(namespace["name"], str):
            raise TypeError(f"Class {name}.name must be of type str")

        if "validator" not in namespace:
            raise TypeError(f"Class {name} must define class variable 'validator'")
        if not isinstance(namespace["validator"], BaseModel):
            raise TypeError(f"Class {name}.validator must be a BaseModel subclass")

        return super().__new__(cls, name, bases, namespace)


class FunctionNode(Node, metaclass=FunctionNodeMeta):
    def prep(self, shared: Dict[str, Any]) -> Tuple[Memory, Connection, Dict]:
        memory = shared["memory"]
        assert isinstance(memory, Memory)

        conn = shared["conn"]
        assert isinstance(conn, Connection)

        arguments = shared["arguments"]
        assert isinstance(arguments, dict)

        return memory, conn, arguments

    def exec(self, inputs: Tuple[Memory, Connection, Dict]) -> Message:
        memory, _, arguments = inputs
        arguments_validated = self.validator.model_validate(arguments)

        return self.exec_function(memory, arguments_validated)

    def exec_function(self, memory: Memory, arguments_validated: Any):
        pass

    def exec_fallback(
        self, prep_res: Tuple[Memory, Connection, Dict], exception: Exception
    ) -> Message:
        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(success=False, result=str(exception)),
        )

    def post(
        self,
        shared: Dict[str, Any],
        prep_res: Tuple[Memory, Connection, Dict],
        exec_res: Message,
    ) -> None:
        assert isinstance(exec_res.content, FunctionResultContent)
        memory, conn, _ = prep_res

        memory.fifo_queue.push_message(exec_res)
        memory.recall_storage.push_message(exec_res)

        conn.send(json.dumps({"message": exec_res.to_intermediate_repr()}))

        if not exec_res.content.success:
            shared["do_heartbeat"] = True


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
                "SELECT optional_function_sets FROM agents WHERE agent_id = ?;",
                (self.agent_id,),
            )[0][0]
        )

    def get_function_nodes(self) -> Dict[str, FunctionNode]:
        function_node_list = []

        # *Load nodes

        base_function_sets_dir = os.path.join(
            os.path.dirname(__file__), "function_sets", "base"
        )

        for function_set_file in os.listdir(base_function_sets_dir):
            if function_set_file.endswith(".py"):
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
                    dict(reversed(node.validator.model_json_schema())), sort_keys=False
                ).strip()
                for node in self.get_function_nodes().values()
            ]
        )
