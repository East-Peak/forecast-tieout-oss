"""Run one company: the simulation, its truth, and (later) the extracts."""

from dataclasses import dataclass

from ..contract.snapshot import Snapshot
from .params import CompanyParams, Intervention
from .sim import Simulation
from .truth import build_truth


@dataclass
class Company:
    params: CompanyParams
    seed: int
    intervention: Intervention
    sim: Simulation
    truth: Snapshot


def run_company(
    params: CompanyParams,
    seed: int,
    intervention: Intervention | None = None,
    extract_days: tuple[int, ...] = (),
) -> Company:
    iv = intervention or Intervention()
    sim = Simulation(params, seed, iv, extract_days).run()
    return Company(params, seed, iv, sim, build_truth(sim))
