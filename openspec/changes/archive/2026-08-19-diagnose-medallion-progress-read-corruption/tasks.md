## 1. Control experiment

- [x] 1.1 Re-run M5 exactly once on `7c4c7c7` and record the result as the control

## 2. Instrument the read

- [x] 2.1 Add `tests/support/progress_read_diagnostics.py` capturing the ten required facts and re-raising
- [x] 2.2 Route `tests/support/medallion_harness.py` and `tests/integration/test_m4_gold_cutover.py` through it
- [x] 2.3 Upload the captured bytes from `ci-m5-gates.yml` on failure
- [x] 2.4 Verify the instrumentation changes no passing behaviour: full suite green, ruff and black green

## 3. Reproduce and classify

- [x] 3.1 Push and run M5 with the instrumentation attached
- [x] 3.2 If it reproduces, download the captured bytes and classify against A/B/C/D/E
- [x] 3.3 If it does not reproduce, run M5 again on the same head and record repeatability across isolated runs
- [x] 3.4 Record the classification with the bytes that support it, or `classification not established`

## 4. Fix, if the evidence names one

- [x] 4.1 Choose the fix from the established class, not from the most plausible story
- [x] 4.2 Add a regression test demonstrated to fail without the fix
- [x] 4.3 Verify: focused reproducer, M3/M4 integration gates, BDD M5 gates, full suite, live M5

## 5. Closure

- [x] 5.1 Write `evidence.md` with the classification, the bytes that support it, and any deviation
- [x] 5.2 Commit, push, confirm live CI green on the pushed SHA
- [x] 5.3 Archive this change, then return to `04-10` without revisiting its disposition
