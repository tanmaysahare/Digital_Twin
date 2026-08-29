"""Loading configuration from YAML, with errors a person can act on.

A validation failure names the file, the field path and what was wrong. A
configuration error that reads like a stack trace costs an engineer an hour on a
plant floor, and the file is the thing they have to fix.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from twin.config.catalogue import SensorCatalogue
from twin.config.line import LineDefinition
from twin.config.sources import SourceMapping

Model = TypeVar("Model", bound=BaseModel)


class ConfigurationError(Exception):
    """A configuration file is missing, malformed, or fails validation."""


def _read_yaml(path: Path) -> object:
    if not path.exists():
        message = f"{path}: no such configuration file"
        raise ConfigurationError(message)
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as malformed:
        message = f"{path}: not valid YAML. {malformed}"
        raise ConfigurationError(message) from malformed


def _describe(path: Path, failure: ValidationError) -> str:
    lines = [f"{path}: {failure.error_count()} problem(s) in this file."]
    for error in failure.errors():
        location = ".".join(str(part) for part in error["loc"]) or "(top level)"
        lines.append(f"  {location}: {error['msg']}")
    return "\n".join(lines)


def _load(path: Path, model: type[Model], what: str) -> Model:
    raw = _read_yaml(path)
    if not isinstance(raw, dict):
        message = f"{path}: expected a {what} mapping, found {type(raw).__name__}"
        raise ConfigurationError(message)
    try:
        return model.model_validate(raw)
    except ValidationError as invalid:
        raise ConfigurationError(_describe(path, invalid)) from invalid


def load_line_definition(path: Path | str) -> LineDefinition:
    """Read and validate a line definition. ONB-01."""
    return _load(Path(path), LineDefinition, "line definition")


def load_source_mapping(path: Path | str) -> SourceMapping:
    """Read and validate a source mapping. ONB-02."""
    return _load(Path(path), SourceMapping, "source mapping")


def load_sensor_catalogue(path: Path | str) -> SensorCatalogue:
    """Read and validate the low-cost sensing catalogue."""
    return _load(Path(path), SensorCatalogue, "sensor catalogue")


def load_config(path: Path | str, model: type[Model], what: str) -> Model:
    """Read and validate any configuration file against a pydantic model.

    The simulator's own parameters use this. They are deliberately not part of
    the `LineDefinition`: the twin loads the line definition, and if the true
    cycle times lived in it the twin would be reading the answer.
    """
    return _load(Path(path), model, what)
