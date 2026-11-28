"""The routing and queue core of the workload contract, pure and period-agnostic.

Demand offered to a team waits in age classes (one class per period of arrival).
Each period the room is given to the oldest class first; when a class is
oversubscribed the room splits across lanes in proportion to class size by the
largest-remainder rule (ties to the earlier lane). Demand not admitted within
`max_age` further periods expires. The daily simulation runs it with one day as
the period; golden fixture B runs it with one month and one retry. Items are
opaque, so the simulation queues leads and the fixture test queues integers.
"""


def largest_remainder(slots: int, sizes: list[int]) -> list[int]:
    """Split `slots` across lanes in proportion to `sizes`, never above a lane's size."""
    total = sum(sizes)
    if total <= slots:
        return list(sizes)
    shares = [slots * s // total for s in sizes]
    leftover = slots - sum(shares)
    by_fraction = sorted(
        range(len(sizes)), key=lambda i: (-(slots * sizes[i] % total), i)
    )
    for i in by_fraction[:leftover]:
        shares[i] += 1
    return shares


def route(room: int, classes: list[list[int]]) -> list[list[int]]:
    """Per-lane takes for each class, oldest class first, until the room is spent."""
    takes = []
    for sizes in classes:
        take = largest_remainder(max(room, 0), sizes)
        room -= sum(take)
        takes.append(take)
    return takes


class RoutingQueue:
    """One team's waiting demand across its lanes."""

    def __init__(self, n_lanes: int, max_age: int):
        self.n_lanes = n_lanes
        self.max_age = max_age
        self._classes: list[list] = []  # [age, [items per lane]], oldest first

    def sizes(self) -> list[int]:
        return [sum(len(c[1][i]) for c in self._classes) for i in range(self.n_lanes)]

    def items(self) -> list[tuple[int, int, object]]:
        """(lane, age, item) for everything waiting, oldest first."""
        return [
            (lane, age, item)
            for age, per_lane in self._classes
            for lane, waiting in enumerate(per_lane)
            for item in waiting
        ]

    def step(self, room: int, arrivals: list[list]) -> tuple[list[list], list[list]]:
        """Admit up to `room` (oldest first), expire what has waited too long, age the rest."""
        self._classes.append([0, [list(a) for a in arrivals]])
        takes = route(room, [[len(w) for w in c[1]] for c in self._classes])
        admitted: list[list] = [[] for _ in range(self.n_lanes)]
        expired: list[list] = [[] for _ in range(self.n_lanes)]
        kept = []
        for cls, take in zip(self._classes, takes, strict=True):
            age, per_lane = cls
            for lane, n in enumerate(take):
                admitted[lane].extend(per_lane[lane][:n])
                per_lane[lane] = per_lane[lane][n:]
            if age >= self.max_age:
                for lane, rest in enumerate(per_lane):
                    expired[lane].extend(rest)
            elif any(per_lane):
                kept.append([age + 1, per_lane])
        self._classes = kept
        return admitted, expired
