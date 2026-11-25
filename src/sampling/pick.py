"""Stratified sampling for compliance audit records.

A record is a mapping with at least ``id`` and ``zone`` keys.  An optional
``weight`` key expresses the audit priority of the record; larger values mean
that the record is more important and should be picked more often.

A policy is a mapping with any of the following keys:

``strata``
    Names of all audit partitions.  Partitions without records are still
    reported as uncovered.
``size``
    Requested number of records per partition.
``fraction``
    Requested fraction of each partition when ``size`` is not supplied.
``seed``
    Default seed carried by the policy.
"""

from __future__ import annotations

import math
import hashlib
from collections.abc import Mapping



class _Rng:
    """Deterministic hash-based pseudo random source (no stdlib random)."""

    def __init__(self, seed):
        self._seed = str(seed).encode("utf-8")
        self._counter = 0
        self._buffer = []

    def _next_float(self):
        if not self._buffer:
            digest = hashlib.sha256(self._seed + b":" + str(self._counter).encode()).digest()
            self._counter += 1
            self._buffer = [
                int.from_bytes(digest[i:i + 4], "big") / 2 ** 32 for i in range(0, 32, 4)
            ]
        return self._buffer.pop(0)

    def random(self):
        return self._next_float()

    def randrange(self, n):
        return int(self._next_float() * n)

    def choice(self, pool):
        return pool[self.randrange(len(pool))]


def strata_of(records):
    """Group records by partition.

    ``records`` may be an iterable of record mappings or an explicit mapping
    from partition names to record lists.  The explicit form can declare a
    partition that currently contains no records.
    """
    if isinstance(records, Mapping):
        return {zone: list(items) for zone, items in records.items()}

    strata = {}
    for record in records:
        zone = record["zone"]
        strata.setdefault(zone, []).append(record)
    return strata


def sample_size(stratum, policy):
    """Return how many records to draw from one partition."""
    if not stratum:
        return 0

    if "size" in policy:
        target = int(policy["size"])
    else:
        fraction = float(policy.get("fraction", 0.5))
        target = int(len(stratum) * fraction)

    # A non-empty partition always contributes at least one record.
    return max(1, min(len(stratum), target))


def _priority(record):
    """Numeric priority used by the weighted draw."""
    try:
        return max(0.0, float(record.get("weight", 1.0)))
    except (TypeError, ValueError):
        return 1.0


def _weighted_draw(records, size, rng):
    pool = list(records)
    size = max(0, min(int(size), len(pool)))
    picked = []
    for _ in range(size):
        total = sum(_priority(record) for record in pool)
        if total <= 0:
            index = rng.randrange(len(pool))
        else:
            point = rng.random() * total
            running = 0.0
            index = len(pool) - 1
            for position, record in enumerate(pool):
                running += _priority(record)
                if point < running:
                    index = position
                    break
        picked.append(pool.pop(index))
    return picked


def weighted_pick(records, size, seed):
    """Draw records using their audit priorities and a deterministic seed."""
    rng = _Rng(seed)
    return _weighted_draw(records, size, rng)


def _zone(record):
    return record["zone"]


def _covered_zones(sampled):
    return {_zone(record) for record in sampled}


def _all_strata(records, policy):
    strata = strata_of(records)
    for zone in policy.get("strata", []) or []:
        strata.setdefault(zone, [])
    return strata


def _uncovered(zones, sampled):
    covered = _covered_zones(sampled)
    return [zone for zone in zones if zone not in covered]


def _sample_with_rng(records, policy, rng):
    strata = _all_strata(records, policy)

    sampled = []
    for zone in sorted(strata):
        items = strata[zone]
        sampled.extend(_weighted_draw(items, sample_size(items, policy), rng))

    return {
        "sampled": sampled,
        "coverage": _uncovered(list(strata), sampled),
        "strata": strata,
        "size": len(sampled),
    }


def sample(records, policy, seed):
    """Build a reproducible sample and report partition coverage."""
    if seed is None:
        seed = policy.get("seed", 0)
    rng = _Rng(seed)
    return _sample_with_rng(records, policy, rng)


def coverage(records, sampled):
    """Return the names of partitions that have no sampled record."""
    strata = strata_of(records)
    covered = _covered_zones(sampled)
    return [zone for zone in strata if zone not in covered]


def dedupe(sampled):
    """Remove repeated records while keeping one record per identifier."""

    def key(record):
        return record["id"] if isinstance(record, Mapping) else record

    unique = {}
    for record in sampled:
        unique[key(record)] = record
    return [unique[item] for item in sorted(unique)]


def validate_policy(policy):
    """Return human readable problems found in a sampling policy."""
    issues = []
    if not policy.get("strata"):
        issues.append("策略缺少分层")
    if policy.get("seed") is None:
        issues.append("策略缺少种子")
    return issues


def sampling_batch(batches, policy, seed):
    """Sample several batches, keeping each batch independent."""
    if isinstance(batches, Mapping):
        items = list(batches.items())
    else:
        items = [(f"batch-{index}", batch) for index, batch in enumerate(batches)]

    if not items:
        return {}

    result = {}
    for name, records in items:
        # Each batch gets a fresh generator so batches never influence
        # one another; identical batches with the same seed match exactly.
        result[name] = _sample_with_rng(records, policy, _Rng(seed))
    return result