"""Every report any test in this package builds must satisfy the report contract.

``build_report`` is wrapped once, here, before the test modules import it, so
the whole suite (some 380 tests over the demo companies and the generated ones:
adopted, not shown and unavailable capacity; with and without a plan; short
history; missing costs and targets) is a validation run of the schema."""

from engine.tests.tieout_core.lanes_support import built  # noqa: F401  (the lanes tests' fixture)
from engine.tieout_core import contract, report

_build_report = report.build_report


def checked_build_report(*args, **kwargs):
    made = _build_report(*args, **kwargs)
    problems = contract.validate(made)
    assert not problems, "report does not satisfy the contract:\n" + "\n".join(
        problems[:10]
    )
    return made


report.build_report = checked_build_report
