from runzi.configuration.arguments import ArgBase, SweptArgs
from pydantic import BaseModel
from math import prod

class SimpleArgs(ArgBase):

    class ComplexThing(BaseModel):
        a: int
        b: str

    param_a: int
    param_b: float
    param_c: str
    param_d: ComplexThing


def test_swept_args():

    data = {
        "title": "simple test",
        "description": "a simple args class",
        "param_a": 1,
        "param_b": 0.1,
        "param_c": "foo",
        "param_d": {"a": 10, "b": "x"}
    }
    prototype = SimpleArgs(**data)
    swept_args = {
        "param_a": [1, 2, 3],
        "param_d": [ {"a": 101, "b": "X"}, {"a": 102, "b": "Y"} ]
    }
    swept = SweptArgs(prototype, swept_args)
    ntasks = len(list(swept.get_tasks()))
    assert ntasks == prod([len(v) for v in swept_args.values()])
