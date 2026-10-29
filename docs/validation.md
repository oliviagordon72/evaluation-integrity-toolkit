# Local validation

Validated on 2026-10-27 using Linux and Python 3.12.14.

| Check | Result |
| --- | --- |
| Ruff lint | Passed |
| Ruff format | Passed |
| pytest | 25 tests passed |
| Eight isolated integrity failure categories | All rejected as expected |
| Actual Inspect mock-provider integration | Passed |
| CLI lifecycle with external connections blocked | Passed |
| Rejected CLI release leaves no output bundle | Passed |

The suite includes unit tests, Hypothesis property tests, integration tests, and a
CLI subprocess end-to-end test. Local tests emitted upstream Inspect/tenacity
deprecation warnings about the `initial` retry parameter; they did not fail.

The delivered source includes an offline demo and a GitHub Actions workflow.
Hosted GitHub Actions and paid-provider evaluations were not run here.
See README.md to rerun validation in your own checkout.
