import json
from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Tuple

from pocketflow import Node
from pydantic import BaseModel
from pydantic._internal._model_construction import ModelMetaclass

from memory import FunctionResultContent, Memory, Message


class FunctionNodeMeta(type):
    def __new__(cls, name, bases, namespace):
        if "name" not in namespace:
            raise TypeError(f"Class {name} must define class variable 'name'")
        if not isinstance(namespace["name"], str):
            raise TypeError(f"Class {name}.name must be of type str")

        if "validator" not in namespace:
            raise TypeError(f"Class {name} must define class variable 'validator'")
        if not isinstance(namespace["validator"], ModelMetaclass):
            print(type(namespace["validator"]))
            raise TypeError(f"Class {name}.validator must be a BaseModel subclass")

        return super().__new__(cls, name, bases, namespace)


class FunctionNode(Node, metaclass=FunctionNodeMeta):
    name = "placeholder"
    validator = BaseModel

    def prep(self, shared: Dict[str, Any]) -> Tuple[Memory, Connection, Dict]:
        memory = shared["memory"]
        assert isinstance(memory, Memory)

        conn = shared["conn"]
        assert isinstance(conn, Connection)

        arguments = shared["arguments"]
        assert isinstance(arguments, dict)

        return memory, conn, arguments

    def exec(self, inputs: Tuple[Memory, Connection, Dict]) -> Message:
        memory, conn, arguments = inputs
        arguments_validated = self.validator.model_validate(arguments)

        return self.exec_function(memory, conn, arguments_validated)

    def exec_function(self, memory: Memory, conn: Connection, arguments_validated: Any):
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

        memory.push_message(exec_res)

        conn.send(json.dumps({"message": exec_res.to_intermediate_repr()}))

        if not exec_res.content.success:
            shared["do_heartbeat"] = True
