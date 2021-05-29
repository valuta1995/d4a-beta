import abc
from typing import Optional

import jsonpickle


class Storable(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def is_sane(self) -> bool:
        raise NotImplementedError()

    @classmethod
    def to_file(cls, path: str, data: 'Storable', max_depth: Optional[int] = None):
        if cls is not data.__class__:
            if cls is Storable.__class__:
                raise Exception("Don't try to store a storable. Store the correct class instead.")
            else:
                raise Exception("Output is not the correct class.")
        if not data.is_sane():
            raise Exception("Refusing to write invalid file.")

        if max_depth is not None:
            payload = jsonpickle.encode(data, indent=2, max_depth=max_depth)
        else:
            payload = jsonpickle.encode(data, indent=2)

        with open(path, mode='w') as out_file:
            out_file.write(payload)

    @classmethod
    def from_file(cls, path: str) -> 'Storable':
        with open(path, mode='r') as in_file:
            payload = in_file.read()
        decoded = jsonpickle.decode(payload)
        if not isinstance(decoded, cls):
            raise TypeError("Input is not the correct class.")
        if not decoded.is_sane():
            raise Exception("Refusing to read invalid file.")
        return decoded
