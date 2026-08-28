"""Configuration models, the loader, and the two line definitions.

T-010, T-011, T-012, T-013.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from twin.config import (
    ConfigurationError,
    load_line_definition,
    load_sensor_catalogue,
    load_source_mapping,
)
from twin.config.line import LineDefinition

REPO_ROOT = Path(__file__).resolve().parent.parent
LINE2 = REPO_ROOT / "config" / "lines" / "line2.yaml"
LINE7 = REPO_ROOT / "config" / "lines" / "line7.yaml"
SIM_SOURCES = REPO_ROOT / "config" / "sources" / "sim.yaml"
CATALOGUE = REPO_ROOT / "config" / "catalogue" / "sensors.yaml"


def _line2_dict() -> dict[str, object]:
    loaded = yaml.safe_load(LINE2.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _written(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "line.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# T-011: the reference line


def test_the_reference_line_loads() -> None:
    line = load_line_definition(LINE2)
    assert line.line_id == "line2"
    assert len(line.stations) == 42
    assert float(line.takt_s) == 60.0


def test_the_reference_line_has_the_specified_tier_split() -> None:
    """PRD.md Section 1. Six dark stations is 14 percent, and it is the point."""
    line = load_line_definition(LINE2)
    assert len(line.stations_of_tier("A")) == 24
    assert len(line.stations_of_tier("B")) == 12
    assert line.stations_of_tier("C") == ("S33", "S34", "S35", "S36", "S37", "S42")


def test_the_reference_line_has_its_zones_gates_and_buffers() -> None:
    line = load_line_definition(LINE2)
    assert tuple(zone.zone_id for zone in line.zones) == ("body", "paint", "final")
    assert tuple(gate.gate_id for gate in line.gates) == ("G1", "G2", "G3")
    assert {gate.gate_id: gate.after for gate in line.gates} == {
        "G1": "S16",
        "G2": "S26",
        "G3": "S42",
    }
    assert len(line.buffers) == 9
    capacities = [item.capacity for item in line.buffers]
    assert min(capacities) == 3
    assert max(capacities) == 12


def test_the_reference_line_reworks_from_g1_into_the_line_and_g3_off_it() -> None:
    line = load_line_definition(LINE2)
    routes = {loop.origin: loop.destination for loop in line.rework}
    assert routes == {"G1": "S12", "G3": "off_line"}


def test_the_reference_line_carries_the_specified_thresholds() -> None:
    """TECHNICAL_SPEC.md Section 12. None of these appears in code."""
    line = load_line_definition(LINE2)
    assert line.forecast.replications == 200
    assert line.forecast.horizon_min == 120
    assert line.forecast.stall_probability_threshold == 0.55
    assert line.drift.require_both is True
    assert line.gates_policy.promotion.min_precision == 0.70
    assert line.gates_policy.demotion.max_precision == 0.55


# ---------------------------------------------------------------------------
# T-012: the second line


def test_the_second_line_loads() -> None:
    line = load_line_definition(LINE7)
    assert line.line_id == "line7"


def test_the_second_line_is_structurally_different() -> None:
    """AC-080. Different on every axis a naive implementation would hard-code."""
    first = load_line_definition(LINE2)
    second = load_line_definition(LINE7)

    assert len(second.stations) != len(first.stations)
    assert len(second.zones) != len(first.zones)
    assert len(second.variants) != len(first.variants)
    assert len(second.shifts) != len(first.shifts)
    assert second.takt_s != first.takt_s
    assert not set(second.station_ids) & set(first.station_ids)

    first_share = len(first.stations_of_tier("C")) / len(first.stations)
    second_share = len(second.stations_of_tier("C")) / len(second.stations)
    assert second_share > first_share


def test_the_second_line_carries_both_dark_station_cases() -> None:
    """One isolated dark station, and a run of four with no scan between."""
    line = load_line_definition(LINE7)
    dark = set(line.stations_of_tier("C"))
    order = line.station_ids

    isolated = [
        station
        for index, station in enumerate(order)
        if station in dark
        and (index == 0 or order[index - 1] not in dark)
        and (index == len(order) - 1 or order[index + 1] not in dark)
    ]
    assert isolated, "no isolated dark station, so the resolvable case is untested"

    longest = 0
    run = 0
    for station in order:
        run = run + 1 if station in dark else 0
        longest = max(longest, run)
    assert longest >= 2, "no adjacent dark stations, so STA-07 is untested"


# ---------------------------------------------------------------------------
# T-010: the loader and its errors


def test_a_missing_file_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="no such configuration file"):
        load_line_definition(tmp_path / "line9.yaml")


def test_malformed_yaml_says_so(tmp_path: Path) -> None:
    path = tmp_path / "line.yaml"
    path.write_text("stations: [S01\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not valid YAML"):
        load_line_definition(path)


def test_an_unknown_key_is_rejected(tmp_path: Path) -> None:
    """A typo that silently does nothing is a plant misconfigured unnoticed."""
    document = _line2_dict()
    document["takt_seconds"] = 60
    with pytest.raises(ConfigurationError, match="takt_seconds"):
        load_line_definition(_written(tmp_path, document))


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        pytest.param(
            lambda d: d.__setitem__("mix", {"V-STD": 0.5, "V-SPT": 0.3, "V-LWB": 0.1}),
            "sum to 1.0",
            id="mix-does-not-sum",
        ),
        pytest.param(
            lambda d: d.__setitem__("mix", {"V-STD": 0.6, "V-SPT": 0.4}),
            "exactly the variants",
            id="mix-misses-a-variant",
        ),
        pytest.param(
            lambda d: d["buffers"].append({"id": "B9", "after": "S99", "capacity": 4}),
            "no station S99",
            id="buffer-after-an-unknown-station",
        ),
        pytest.param(
            lambda d: d["gates"].append(
                {"id": "G4", "after": "S99", "name": "Nowhere"}
            ),
            "no station S99",
            id="gate-after-an-unknown-station",
        ),
        pytest.param(
            lambda d: d["rework"].append({"from": "G9", "to": "S12"}),
            "not a gate",
            id="rework-from-an-unknown-gate",
        ),
        pytest.param(
            lambda d: d["rework"].append({"from": "G1", "to": "S99"}),
            "neither a station",
            id="rework-to-an-unknown-station",
        ),
        pytest.param(
            lambda d: d["zones"].__setitem__(
                0, {"id": "body", "name": "Body", "stations": ["S16", "S01"]}
            ),
            "comes before",
            id="zone-runs-backwards",
        ),
        pytest.param(
            lambda d: d["stations"].append(
                {"id": "S01", "tier": "A", "is_manual": False}
            ),
            "appears more than once",
            id="duplicate-station",
        ),
        pytest.param(
            lambda d: d["stations"][0].__setitem__("tier", "D"),
            "tier",
            id="unknown-tier",
        ),
        pytest.param(
            lambda d: d["gates_policy"]["demotion"].__setitem__("max_precision", 0.9),
            "must be below",
            id="demotion-above-promotion",
        ),
    ],
)
def test_invalid_configuration_names_the_field(
    tmp_path: Path, mutate: object, expected: str
) -> None:
    document = _line2_dict()
    mutate(document)  # type: ignore[operator]
    with pytest.raises(ConfigurationError) as failure:
        load_line_definition(_written(tmp_path, document))
    message = str(failure.value)
    assert expected in message
    assert str(tmp_path) in message, "the error must name the file to fix"


def test_the_last_station_cannot_have_a_transport_time(tmp_path: Path) -> None:
    document = _line2_dict()
    document["stations"][-1]["transport_to_next_s"] = 4.2
    with pytest.raises(ConfigurationError, match="last station"):
        load_line_definition(_written(tmp_path, document))


def test_zones_must_cover_every_station(tmp_path: Path) -> None:
    document = _line2_dict()
    document["zones"][-1]["stations"] = ["S27", "S40"]
    with pytest.raises(ConfigurationError, match="every station exactly once"):
        load_line_definition(_written(tmp_path, document))


def test_a_line_definition_is_immutable() -> None:
    line = load_line_definition(LINE2)
    with pytest.raises(ValueError, match="frozen"):
        line.takt_s = 55.0  # type: ignore[misc]


def test_unknown_station_lookup_names_the_line() -> None:
    line = load_line_definition(LINE2)
    with pytest.raises(KeyError, match="line2"):
        line.station("S99")


# ---------------------------------------------------------------------------
# T-010: the source mapping


def test_the_simulator_source_mapping_loads() -> None:
    mapping = load_source_mapping(SIM_SOURCES)
    assert mapping.line_id == "line2"
    assert mapping.adapter == "sim"


def test_the_source_mapping_covers_every_canonical_event_type() -> None:
    """ING-01. Twelve types, and the simulator has to be able to emit them all."""
    mapping = load_source_mapping(SIM_SOURCES)
    assert len(mapping.event_types()) == 12


def test_a_duplicate_native_reference_is_rejected(tmp_path: Path) -> None:
    document = yaml.safe_load(SIM_SOURCES.read_text(encoding="utf-8"))
    document["mappings"].append(document["mappings"][0])
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="mapped more than once"):
        load_source_mapping(path)


# ---------------------------------------------------------------------------
# T-013: the sensing catalogue


def test_the_catalogue_loads_with_six_options() -> None:
    catalogue = load_sensor_catalogue(CATALOGUE)
    assert len(catalogue.options) == 6


def test_every_catalogue_entry_carries_a_source() -> None:
    """T-013. A cost shown to a plant manager can be traced or it does not ship."""
    catalogue = load_sensor_catalogue(CATALOGUE)
    for option in catalogue.options:
        assert option.source.strip(), f"{option.option_id} has no source"


def test_every_indicative_cost_is_labelled_as_an_assumption() -> None:
    """We have no quotations. The catalogue says so rather than implying one."""
    catalogue = load_sensor_catalogue(CATALOGUE)
    for option in catalogue.options:
        assert "Assumption" in option.source, (
            f"{option.option_id} states a cost without saying where it came from. "
            f"RESEARCH_SOURCES.md allows a measured value, a read source, or an "
            f"assumption labelled as one."
        )


def test_a_dark_manual_station_has_something_to_recommend() -> None:
    catalogue = load_sensor_catalogue(CATALOGUE)
    options = catalogue.applicable("C", is_manual=True)
    assert options, "nothing in the catalogue fits a dark manual station"
    assert "scan_point" in {option.option_id for option in options}


def test_the_catalogue_rejects_a_duplicate_option(tmp_path: Path) -> None:
    document = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    document["options"].append(document["options"][0])
    path = tmp_path / "sensors.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="appears more than once"):
        load_sensor_catalogue(path)


# ---------------------------------------------------------------------------
# The rule the whole configuration boundary exists to serve


def test_both_lines_load_through_the_same_code_path() -> None:
    """ONB-04. Adding a line is a file, not a branch."""
    for path in (LINE2, LINE7):
        assert isinstance(load_line_definition(path), LineDefinition)
