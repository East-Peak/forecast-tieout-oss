"""YAML with line numbers: every mapping and sequence remembers where each of its items began."""

import yaml


class ConfigError(ValueError):
    """A catalog problem, named by file, line and offending key."""

    def __init__(self, file: str, line: int, key: str | None, message: str):
        where = f"{file}:{line}" + (f": key '{key}'" if key else "")
        super().__init__(f"{where}: {message}")
        self.file, self.line, self.key, self.message = file, line, key, message


class LDict(dict):
    line: int = 0

    def __init__(self, *args, lines=None, line=0):
        super().__init__(*args)
        self.lines = lines or {}
        self.line = line

    def at(self, key) -> int:
        return self.lines.get(key, self.line)


class LList(list):
    def __init__(self, *args, lines=None, line=0):
        super().__init__(*args)
        self.lines = lines or []
        self.line = line

    def at(self, index) -> int:
        return self.lines[index] if index < len(self.lines) else self.line


class _Loader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    loader.flatten_mapping(node)
    out = LDict(line=node.start_mark.line + 1)
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in out:
            raise yaml.YAMLError(
                f"duplicate key {key!r} at line {key_node.start_mark.line + 1}"
            )
        out[key] = loader.construct_object(value_node, deep=True)
        out.lines[key] = key_node.start_mark.line + 1
    return out


def _sequence(loader, node):
    out = LList(line=node.start_mark.line + 1)
    for item in node.value:
        out.append(loader.construct_object(item, deep=True))
        out.lines.append(item.start_mark.line + 1)
    return out


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG, _sequence)


def load_yaml(text: str, file: str = "<catalog>") -> LDict:
    try:
        data = yaml.load(text, _Loader)
    except yaml.MarkedYAMLError as err:
        mark = err.problem_mark
        raise ConfigError(
            file, (mark.line + 1) if mark else 0, None, f"invalid YAML: {err.problem}"
        ) from err
    except yaml.YAMLError as err:
        raise ConfigError(file, 0, None, str(err)) from err
    if not isinstance(data, LDict):
        raise ConfigError(file, 1, None, "a catalog is a mapping at the top level")
    return data
