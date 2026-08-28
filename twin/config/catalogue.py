"""The low-cost sensing catalogue.

What the twin is allowed to recommend when a blind spot limits a prediction, and
what each option indicatively costs. Every entry carries a `source` field so a
number shown to a plant manager can be traced rather than trusted. Where the
source is our own assumption, it says so in those words.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, model_validator

from twin.config.line import Strict, Tier

Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class ConfidenceModel(Strict):
    """What installing this option is projected to do to an estimate.

    A projection, not a measurement. SNS-06 validates it after an install by
    comparing projected against realised, and until an install has happened the
    interface shows it as an estimate with a range.
    """

    # The confidence the limiting estimate is projected to reach.
    projected_confidence: Probability
    # The uncertainty on that projection, plus and minus.
    projected_confidence_margin: Probability = 0.10
    # What the option resolves, in the words the interface uses.
    resolves: str = Field(min_length=1)


class SensorOption(Strict):
    """One item a plant could fit in a scheduled window."""

    option_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    signal_provided: str = Field(min_length=1)
    indicative_cost_usd: float = Field(ge=0.0)
    install_hours: float = Field(ge=0.0)
    requires_window: bool
    # Which observability tiers this option can lift, and whether it needs the
    # station to be manual or automated.
    applicable_to: tuple[Tier, ...] = Field(min_length=1)
    applies_to_manual: bool = True
    applies_to_automated: bool = True
    confidence_model: ConfidenceModel
    # Where the cost came from. Never blank, and an assumption says so.
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def applies_somewhere(self) -> Self:
        """An option that fits nothing cannot be recommended."""
        if not (self.applies_to_manual or self.applies_to_automated):
            message = (
                f"{self.option_id}: applies to neither manual nor automated "
                f"stations, so it can never be recommended"
            )
            raise ValueError(message)
        return self


class SensorCatalogue(Strict):
    """Every sensing option the recommender may choose from."""

    version: str = Field(min_length=1)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    note: str = Field(min_length=1)
    options: tuple[SensorOption, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def option_ids_are_unique(self) -> Self:
        """Two options cannot share an identifier."""
        seen: set[str] = set()
        for option in self.options:
            if option.option_id in seen:
                message = f"options: {option.option_id} appears more than once"
                raise ValueError(message)
            seen.add(option.option_id)
        return self

    def option(self, option_id: str) -> SensorOption:
        """One option by identifier."""
        for candidate in self.options:
            if candidate.option_id == option_id:
                return candidate
        message = f"no sensing option {option_id} in the catalogue"
        raise KeyError(message)

    def applicable(self, tier: Tier, *, is_manual: bool) -> tuple[SensorOption, ...]:
        """Every option that could be fitted to a station of this kind."""
        return tuple(
            option
            for option in self.options
            if tier in option.applicable_to
            and (option.applies_to_manual if is_manual else option.applies_to_automated)
        )
