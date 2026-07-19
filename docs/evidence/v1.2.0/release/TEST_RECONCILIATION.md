# Pytest Collection Reconciliation

RECONCILIATION_STATUS: PASS

## Current commands

```text
.venv\Scripts\python.exe -m pytest --collect-only -q
.venv\Scripts\python.exe -c "import ast,pathlib,re,collections; files=sorted(pathlib.Path('tests').glob('test_*.py')); funcs=[]; [funcs.extend((str(p).replace('\\','/'),n.name) for n in ast.parse(p.read_text(encoding='utf-8-sig')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')) for p in files]; print('SOURCE_TEST_FILES',len(files)); print('SOURCE_TEST_FUNCTIONS',len(funcs)); raw=pathlib.Path('docs/evidence/v1.2.0/release/test_collection_output.txt').read_text(encoding='utf-8-sig'); names=re.findall(r'<Function (test_[^>]+)>',raw); print('COLLECTED_FUNCTION_ITEMS',len(names)); base=[n.split('[')[0] for n in names]; counts=collections.Counter(base); print('EXPANDED_BASES'); [print(k, v) for k,v in sorted(counts.items()) if v>1]; print('FUNCTION_ITEM_DELTA',len(names)-len(funcs))"
```

The collector command exited `0`. Its complete output is retained in
`test_collection_output.txt` with the exact command and exit code.

## Current result

| Measure | Current value |
|---|---:|
| Collected test files | 21 |
| Source `test_*` function definitions | 156 |
| Pytest function items | 158 |
| Parameter-expansion delta | 2 |

The collector reported: `158 tests collected in 0.86s`.

## Parameterized item accounting

Two source functions each expand to two pytest items, adding one item apiece:

1. `tests/test_stability_phase.py::test_real_wrappers_terminate_their_owned_trees`
   expands to `[ffmpeg]` and `[whisper]`.
2. `tests/test_ui_v11.py::test_current_slide_drives_preview_and_scroll`
   expands to `[grid]` and `[list]`.

Therefore `156 source functions + 2 additional parameter variants = 158
collected pytest items`.

## Baseline reconciliation

- The research baseline counted 149 source functions in 20 test files. The two
  parameter expansions above explain the corresponding 151 collected items.
- Plan 01-01 added three release regression functions to
  `tests/test_packaging_and_safety.py`, taking the tree to 152 source functions
  and 154 collected items.
- Plan 01-02 Task 1 added the four authorized alignment functions in the new
  `tests/test_alignment.py`, taking the current tree to 156 source functions in
  21 files and 158 collected items.

The illustrative `153 functions / 155 items` estimate in the plan accounted
for the four alignment nodes but not the three already-landed Plan 01-01
release regression nodes. The current collector is authoritative. No test was
renamed, deleted, weakened, or altered to force a historical count.
