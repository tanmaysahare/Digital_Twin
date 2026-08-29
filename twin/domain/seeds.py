"""Deterministic seeding.

NFR-07 requires that a seeded scenario replay produces identical results, so
every stochastic path in this repository draws from a generator built here. The
rule and its lint check are in CODING_STANDARDS.md Section 1.4.

Python's built-in `hash` is salted per process for strings, so two runs of the
same scenario in two processes would disagree. Blake2b is stable across
processes, platforms and Python versions, which is what makes an evaluation
number reproducible on someone else's laptop.
"""

from __future__ import annotations

import hashlib

import numpy as np

# 63 bits, so the value is a positive signed 64-bit integer and survives a round
# trip through a database column without a sign surprise.
_SEED_BITS = 63
_SEED_MASK = (1 << _SEED_BITS) - 1


def seed_for(*parts: object) -> int:
    """Build a stable seed from any sequence of identifying parts.

    Args:
        *parts: the identity of the draw, for example `(cycle_id, replication)`
            or `(run_seed, "station", station_id)`. Parts are rendered with
            `str` and joined, so two different tuples cannot collide unless
            their rendered forms are equal.

    Returns:
        A non-negative integer below 2**63.
    """
    material = "\u001f".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.blake2b(material, digest_size=8).digest()
    return int.from_bytes(digest, "big") & _SEED_MASK


def generator_for(*parts: object) -> np.random.Generator:
    """A NumPy generator seeded on the identity of the draw."""
    return np.random.default_rng(seed_for(*parts))
