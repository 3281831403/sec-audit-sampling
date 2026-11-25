import time
from collections import Counter

from sampling import sample, sampling_batch


def record(identifier, zone, weight=1):
    return {"id": identifier, "zone": zone, "weight": weight}


def ids(records):
    return [item["id"] for item in records]


def test_stratified_sampling_covers_every_zone():
    records = [
        record("a-1", "north"),
        record("b-1", "south"),
        record("c-1", "east"),
    ]
    policy = {"size": 1, "seed": 11}

    result = sample(records, policy, 11)
    sampled_zones = {item["zone"] for item in result["sampled"]}

    assert sampled_zones == {"north", "south", "east"}


def test_each_stratum_contributes_at_least_one_record():
    records = [
        record("big-1", "big"),
        record("big-2", "big"),
        record("big-3", "big"),
        record("small-1", "small"),
    ]
    policy = {"fraction": 0.25, "seed": 3}

    result = sample(records, policy, 3)
    counts = Counter(item["zone"] for item in result["sampled"])

    assert counts["big"] >= 1
    assert counts["small"] >= 1


def test_same_seed_produces_same_sample():
    records = [
        record(f"r-{index}", ("north", "south", "east")[index % 3])
        for index in range(18)
    ]
    policy = {"fraction": 0.4, "seed": 5}

    results = []
    for _ in range(3):
        results.append(ids(sample(records, policy, 5)["sampled"]))
        time.sleep(0.005)

    assert all(result == results[0] for result in results[1:])


def test_sample_is_subset_of_population():
    records = [
        record(f"north-{index}", "north") for index in range(3)
    ] + [
        record(f"south-{index}", "south") for index in range(3)
    ]
    policy = {"fraction": 2.0, "seed": 9}

    result = sample(records, policy, 9)
    sampled_ids = ids(result["sampled"])
    population_ids = {item["id"] for item in records}

    assert set(sampled_ids) <= population_ids
    assert len(sampled_ids) <= len(population_ids)


def test_two_batches_are_independent():
    batch = [record(f"r-{index}", "north") for index in range(5)]
    policy = {"size": 2, "seed": 17}

    result = sampling_batch([batch, batch], policy, 17)

    assert ids(result["batch-0"]["sampled"]) == ids(result["batch-1"]["sampled"])