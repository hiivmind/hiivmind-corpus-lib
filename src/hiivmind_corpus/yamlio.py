"""YAML in and out: the loader and the one canonical dump style."""

from datetime import datetime
from typing import Any

import yaml

from .errors import InvalidFile
from .schema import stamp


class _Dumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def ignore_aliases(self, data):
        return True


def _represent_stamp(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", stamp(value), style='"')


_Dumper.add_representer(tuple, lambda d, v: d.represent_list(list(v)))
_Dumper.add_representer(type(None), lambda d, v: d.represent_scalar("tag:yaml.org,2002:null", "null"))
_Dumper.add_representer(datetime, _represent_stamp)


def load_yaml(text: str, file: str) -> object:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise InvalidFile(file, "", f"not valid YAML: {e}") from e
    return {} if data is None else data


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=2**31,
                     default_flow_style=False)
