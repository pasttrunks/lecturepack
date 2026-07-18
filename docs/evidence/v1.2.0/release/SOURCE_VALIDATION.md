# Source Validation
COLLECTION_COMMAND: .venv\Scripts\python.exe -m pytest --collect-only -q
COLLECTION_EXIT_CODE: 0
COLLECTION_STATUS: PASS
COLLECTION_LOG: test_collection_output.txt

## Collection reconciliation

SOURCE_TEST_FILES: 21
SOURCE_TEST_FUNCTIONS: 156
COLLECTED_TEST_ITEMS: 158
PARAMETER_EXPANSION_DELTA: 2
RECONCILIATION_STATUS: PASS
RECONCILIATION_REPORT: TEST_RECONCILIATION.md

The 149/151 research baseline is reconciled as 149 source functions plus two
parameter variants. Three Plan 01-01 release tests and four Plan 01-02
alignment tests produce the current 156/158 totals. No test was modified to
match the remembered count.

## Full pytest gate

FULL_PYTEST_COMMAND: .venv\Scripts\python.exe -m pytest -v
FULL_PYTEST_EXIT_CODE: 0
FULL_PYTEST_STATUS: PASS
FULL_PYTEST_RESULT: 158 passed in 113.56s (0:01:53)
FULL_PYTEST_WARNINGS: none
FULL_PYTEST_REGRESSION_WARNING: none
FULL_PYTEST_LOG: full_pytest_output.txt
MAPPED_PYTEST_NODES: 37
MISSING_COLLECTION: none
MISSING_PASS: none

## Development self-test gate

SELFTEST_COMMAND: .venv\Scripts\python.exe -m lecturepack --selftest
SELFTEST_TIMEOUT_SECONDS: 120
SELFTEST_TIMEOUT: false
SELFTEST_EXIT_CODE: 0
SELFTEST_STATUS: PASS
SELFTEST_RESULT: LecturePack v1.2.0 launched, cv2 5.0.0, PySide6 6.11.1, offscreen OK
SELFTEST_LOG: development_selftest_output.txt

## Architecture and privacy audit gate

AUDIT_COMMAND: .venv\Scripts\python.exe -c "exec(compile(open(r'docs\evidence\v1.2.0\release\.architecture_privacy_audit.py', encoding='utf-8').read(), r'docs\evidence\v1.2.0\release\.architecture_privacy_audit.py', 'exec'))"
AUDIT_TIMEOUT_SECONDS: 120
AUDIT_TIMEOUT: false
AUDIT_EXIT_CODE: 1
ARCHITECTURE_CHECK: FAIL
ARCHITECTURE_VIOLATION_COUNT: 47
PRIVACY_CHECK: PASS
PRIVACY_VIOLATION_COUNT: 0
AUDIT_LOG: architecture_privacy_audit_output.txt

The missing architecture contract is strict adjacent-layer dependency
direction. The read-only AST audit found controllers importing infrastructure
directly and UI modules importing services/infrastructure directly. Fixing
those 47 imports requires a production architecture refactor outside this
evidence-only plan's permitted files. The audit was not narrowed to manufacture
a passing result.

## Validation scope and outcome

TRACEABILITY_STATUS: GAP
OVERALL_STATUS: BLOCKED

This evidence does not claim live Groq validation, real lecture-media
validation, or owner-specific installed-package validation. The deterministic
fake-provider and repository test surfaces passed, but the architecture
acceptance gate prevents release evidence from being marked complete.
