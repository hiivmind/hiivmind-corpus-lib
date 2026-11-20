"""The canonical reader and mapper over frozen dataclasses.

A schema dataclass lists its known fields in canonical order and ends with
`extra: tuple[tuple[str, Any], ...] = ()`, the unknown keys in the order found.
Field metadata: `nullable` (an explicit null reads as NULL), `key` (the file key),
`omit_default` (a value equal to the default is not written). A class may name
`reserved` keys that are consumed and not kept.
"""

import dataclasses
import types
import typing
from datetime import UTC, date, datetime
from typing import Any

from .errors import InvalidFile


class Null:
    """An explicit `null` in a file (as opposed to `None`: absent)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "NULL"

    def __bool__(self):
        return False

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def __reduce__(self):
        return "NULL"


NULL = Null()

_KIND = {str: "a string", int: "an integer", bool: "a boolean", datetime: "a timestamp"}


def _found(value: Any) -> str:
    if isinstance(value, dict):
        return "a mapping"
    if isinstance(value, (list, tuple)):
        return "a list"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int):
        return "an integer"
    if isinstance(value, float):
        return "a number"
    if isinstance(value, str):
        return "a string"
    return type(value).__name__


def _join(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


def _at(where: str, index: int) -> str:
    return f"{where}[{index}]"


def parse_timestamp(value: Any, file: str, where: str) -> datetime:
    if isinstance(value, datetime):
        when = value
    elif isinstance(value, date):
        when = datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        try:
            when = datetime.fromisoformat(value.strip())
        except ValueError:
            raise InvalidFile(file, where, f"`{where}` is not a timestamp: {value!r}") from None
    else:
        raise InvalidFile(file, where, f"`{where}` must be a timestamp, found {_found(value)}")
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone(UTC)


def stamp(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_union(tp: Any) -> bool:
    return typing.get_origin(tp) in (typing.Union, types.UnionType)


def _unwrap(tp: Any) -> Any:
    """Drop `None` and `Null` from a union; a single member is the type."""
    if _is_union(tp):
        rest = [a for a in typing.get_args(tp) if a is not type(None) and a is not Null]
        if len(rest) == 1:
            return rest[0]
        raise TypeError(f"unsupported annotation {tp!r}")
    return tp


def _is_schema(tp: Any) -> bool:
    return isinstance(tp, type) and dataclasses.is_dataclass(tp)


def _convert(tp: Any, value: Any, file: str, where: str) -> Any:
    tp = _unwrap(tp)
    origin = typing.get_origin(tp)
    if tp is Any:
        return value
    if tp is bool:
        if isinstance(value, bool):
            return value
        raise InvalidFile(file, where, f"`{where}` must be a boolean, found {_found(value)}")
    if tp is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise InvalidFile(file, where, f"`{where}` must be an integer, found {_found(value)}")
    if tp is str:
        if isinstance(value, str):
            return value
        raise InvalidFile(file, where, f"`{where}` must be a string, found {_found(value)}")
    if tp is datetime:
        return parse_timestamp(value, file, where)
    if _is_schema(tp):
        return read(tp, value, file, where)
    if origin is dict:
        _, vt = typing.get_args(tp)
        if not isinstance(value, dict):
            raise InvalidFile(file, where, f"`{where}` must be a mapping, found {_found(value)}")
        if vt is Any:
            return dict(value)
        return {k: _convert(vt, v, file, _join(where, str(k))) for k, v in value.items()}
    if origin is tuple:
        et = typing.get_args(tp)[0]
        if not isinstance(value, list):
            raise InvalidFile(file, where, f"`{where}` must be a list, found {_found(value)}")
        out = []
        for i, item in enumerate(value):
            here = _at(where, i)
            if et is str:
                if isinstance(item, bool):
                    item = "true" if item else "false"
                elif isinstance(item, (int, float)):
                    item = str(item)
                elif not isinstance(item, str):
                    raise InvalidFile(file, here, f"`{here}` must be text, found {_found(item)}")
                out.append(item)
            else:
                out.append(_convert(et, item, file, here))
        return tuple(out)
    raise TypeError(f"unsupported annotation {tp!r}")


def _nullable(f: dataclasses.Field) -> bool:
    return bool(f.metadata.get("nullable"))


def _default(f: dataclasses.Field, file: str, where: str) -> Any:
    if f.default is not dataclasses.MISSING:
        return f.default
    if f.default_factory is not dataclasses.MISSING:
        return f.default_factory()
    key = f.metadata.get("key", f.name)
    raise InvalidFile(file, _join(where, key), f"`{_join(where, key)}` is required")


def read(cls, data: Any, file: str, where: str = ""):
    if not isinstance(data, dict):
        place = f"`{where}`" if where else "the file"
        raise InvalidFile(file, where, f"{place} must be a mapping, found {_found(data)}")
    hints = typing.get_type_hints(cls)
    reserved = getattr(cls, "reserved", ())
    kwargs: dict[str, Any] = {}
    known: set[str] = set(reserved)
    for f in dataclasses.fields(cls):
        if f.name == "extra":
            continue
        key = f.metadata.get("key", f.name)
        known.add(key)
        if key not in data:
            kwargs[f.name] = _default(f, file, where)
        elif data[key] is None:
            kwargs[f.name] = NULL if _nullable(f) else _default(f, file, where)
        else:
            kwargs[f.name] = _convert(hints[f.name], data[key], file, _join(where, key))
    if any(f.name == "extra" for f in dataclasses.fields(cls)):
        kwargs["extra"] = tuple((k, v) for k, v in data.items() if k not in known)
    return cls(**kwargs)


def _plain(value: Any) -> Any:
    if value is NULL:
        return None
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return mapping(value)
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def mapping(obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in dataclasses.fields(obj):
        if f.name == "extra":
            continue
        value = getattr(obj, f.name)
        if value is None:
            continue
        if f.metadata.get("omit_default"):
            if f.default is not dataclasses.MISSING:
                default = f.default
            elif f.default_factory is not dataclasses.MISSING:
                default = f.default_factory()
            else:
                default = dataclasses.MISSING
            if value == default:
                continue
        out[f.metadata.get("key", f.name)] = _plain(value)
    for k, v in getattr(obj, "extra", ()):
        out[k] = _plain(v)
    return out
