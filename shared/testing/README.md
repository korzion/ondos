# shared/testing

Common base for every module's `run_test.py` (section 3).

```
python run_test.py --list
python run_test.py <TEST-ID> [--input DIR] [--host H] [--port P]
```

Prints `PASS` or `FAIL` for every check and `<TEST-ID>: PASS|FAIL` at the end (exit code 0 / 1; 2 = not implemented yet). `--input` lets the instructor give a different folder of inputs without changing code.

Writing a test:

```python
@suite.test("D-T5", "PID output", requirement="D-R5")
def d_t5(t):
    cases = t.load_jsonl("cases.jsonl")                 # from fixtures/D-T5/
    for c in cases:
        expected = my_reference_pid(c)                  # computed by the test itself
        t.check(f"case {c['name']}", abs(run_module(c) - expected) < 1e-6, f"{run_module(c)} vs {expected}")
```

Helpers on `t`: `check`, `load_json`, `load_jsonl`, `load_csv`, `play_fixture` (playback tool in fixture mode), `observe` (collect bus messages for a while), `checklist` (manual checks answered y/n), `require_broker`.

Rules: the expected result is computed by the test (rule checks or a small independent formula), never by the module's own code; a module test never needs another module. Each demo ends with a deliberately broken input or build that gives FAIL.
