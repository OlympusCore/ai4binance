---
document_id: AI4B-ENG-STD-001
title: AI4BINANCE Python Clean Code and VS Code Development Guide
document_type: STANDARD
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: engineering_python_clean_code_vscode_development
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/standards/standard_engineering_python_clean_code_vscode_development.md
---

# PYTHON CLEAN CODE, PEP 8 AND VS CODE DEVELOPMENT GUIDE

## ELI10

This file is the coding-quality rulebook. It tells contributors how Python code should be written, checked, and kept simple without granting trading authority.


> **ELI5:** This file is a "how to write code?" rulebook; it is not a feature status report.
> It contains current quality commands and results in the root `README.md`.

Apply the following rules compulsorily in all Python code written, edited, or refactored in this project.

## 1. Basic Coding Principles

Code must:

* It should be simple, readable, understandable, and maintainable.
* It should be written in accordance with the PEP 8 coding standard.
* The PEP 257 docstring standard should be followed.
* The principles of KISS, DRY, YAGNI, and SOLID should be applied in balance.
* Excessive abstraction, over-engineering, and complex design patterns should be avoided.
* The simplest, reliable, and testable solution that solves the current problem should be preferred.
* Repeated code should be separated into common functions, classes, or modules.
* Unused code, imports, variables, functions, and comments should not be left behind.
* Temporary solutions, fake data, placeholder code, and silent error-absorbing structures should not be used.

## 2. Code Structure

Each function and class should have only a single primary responsibility.

The following limits should be aimed for:

* Functions should preferably be shorter than 30 lines.
* Classes should not be unnecessarily expanded.
* The depth of nested conditions and loops should not exceed three levels as much as possible.
* Long functions should be divided into meaningful sub-functions.
* Global variable usage should be avoided.
* Constant values should be defined as `UPPER_CASE` named constants.
* `pathlib.Path` should be used for file paths.
* `with` context manager should be preferred for resource management.
* `dataclass`, `TypedDict`, `Enum`, or Pydantic models should be used when appropriate for data transfer.
* Business logic should be separated from the user interface, API, file system, and data access layers.

## 3. Naming Rules

Names should be clear, descriptive, and purpose-oriented.

* Variables and functions: `snake_case`
* Classes: `PascalCase`
* Constants: `UPPER_CASE`
* Private member variables: `_leading_underscore`
* Python files: `snake_case.py`

Avoid ambiguous type names such as:

* `data`
* `temp`
* `value`
* `result`
* `item`
* `obj`
* `x`
* `foo`
* `bar`

Use context-specific names instead:

```python
validated_orders
monthly_incident_count
configuration_path
risk_assessment_result
```

Allow single-character variables only in short and clear loops.

## 4. Type Safety

Use type hints for all new or modified functions.

```python
def calculate_total_cost(
    unit_price: float,
    quantity: int,
) -> float:
    return unit_price * quantity
```

Apply the following rules:

* Type function parameters and return values.
* Avoid the use of `Any` unnecessarily.
* Explicitly handle `Optional` cases.
* Create type aliases for complex types.
* Use modern Python types like `list[str]`, `dict[str, int]` when possible.
* Specify `-> None` for functions that do not have a return type.
* Write code compatible with Pyright or MyPy for type checking.

## 5. Function Design

Functions:

* Should perform only one task.
* Should produce clear input and output.
* Should not create hidden side effects.
* It should not accept an excessive number of parameters.
* Multiple behaviors should not be loaded using boolean parameters.
* It should be designed as a pure function whenever possible.
* Complex nested conditions should be reduced by using early returns.

Preferred structure:

```python
def process_record(record: Record) -> ProcessedRecord:
    if not record.is_valid:
        raise InvalidRecordError("Record validation failed.")

    normalized_record = normalize_record(record)
    return transform_record(normalized_record)
```

Structure to be avoided:

```python
def process_record(record, mode=False, flag=True):
    if record:
        if mode:
            if flag:
                ...
```

## 6. Error Handling

* `except Exception:` should be used only at mandatory top-level boundaries.
* Bare `except:` should not be used.
* Errors should not be silently suppressed.
* Each expected error type should be caught separately.
* Meaningful custom exception classes should be created.
* Error messages should be clear, contextual, and actionable.
* Contextual logs should be recorded when an error occurs, but sensitive information such as passwords, tokens, or personal data should not be logged.
* Unnecessary exception wrapping that hides the root cause of the error should be avoided.

```python
try:
    configuration = load_configuration(configuration_path)
except FileNotFoundError as exc:
    raise ConfigurationError(
        f"Configuration file not found: {configuration_path}"
    ) from exc
```

## 7. Logging

Use the standard `logging` module instead of `print()` in production code.

```python
import logging

logger = logging.getLogger(__name__)
```

Log levels should be used appropriately:

* `DEBUG`: Technical diagnostic information
* `INFO`: Normal flow of operations
* `WARNING`: Operation can continue but requires attention
* `ERROR`: The operation has failed
* `CRITICAL`: Serious error that affects system operation

Passwords, API keys, access tokens, personal data, or sensitive information should not be logged.

## 8. Documentation and Comments

Docstring should be used in the following cases:

* Public functions
* Public classes
* Complex modules
* Difficult-to-understand business rules
* External-facing API components

Docstring should explain the purpose, parameters, return value, and important error conditions, rather than repeating what the code does.

```python
def calculate_risk_score(
    likelihood: int,
    severity: int,
) -> int:
    """Calculate the risk score from likelihood and severity.

    Args:
        likelihood: Probability rating between 1 and 5.
        severity: Consequence rating between 1 and 5.

    Returns:
        Calculated risk score.

    Raises:
        ValueError: If either rating is outside the accepted range.
    """
```

Comments:

* It should explain why the code is structured that way, not just what it does.
* Outdated or unnecessary comments should not be left.
* Commented-out old code should not be kept; version history should be managed via Git.

## 9. Import Order

Imports should be ordered as follows:

1. Python standard libraries
2. Third-party packages
3. Project internal modules

There should be a blank line between groups.

Wildcard imports should not be used:

```python
from module import *
```

Circular imports should be avoided. Import order should be validated using Ruff or isort.

## 10. Security

* Passwords, API keys, tokens, and connection details should not be written into source code.
* Sensitive configurations should be retrieved through environment variables or secure secret management.
* User inputs should be validated.
* File paths should not be used without verification.
* Parameterized queries should be used in SQL queries.
* `eval()` and `exec()` should not be used.
* User input should not be directly concatenated into shell commands.
* The use of `shell=True` should not be the default in `subprocess` usage.
* Untrusted pickle files should not be loaded.
* Sensitive information should not be exposed in logs and error messages.

## 11. Testability

Test cases suitable for new functions should be prepared.

In tests:

* `pytest` should be used.
* Normal scenarios should be tested.
* Boundary values should be tested.
* Invalid inputs should be tested.
* Expected exception scenarios should be tested.
* The file system, network, and external services should be mocked when necessary.
* Tests should be independent of each other.
* Test results should not depend on the execution order.
* When a bug is fixed, regression testing should be added if possible.

Test names should describe behavior:

```python
def test_calculate_risk_score_rejects_out_of_range_likelihood() -> None:
    ...
```

## 12. Code Formatting and Quality Tools

Create code that is compatible with the following tools:

* Ruff: linting, import formatting, and basic code quality
* Black or Ruff formatter: automatic formatting
* Pyright or MyPy: static type checking
* Pytest: tests
* Bandit: basic security checks
* pre-commit: pre-commit quality checks

Recommended check order:

```bash
ruff format .
ruff check . --fix
pytest
pyright
```

Do not consider the task completed until code quality checks are passed.

## 13. PEP 8 Formatting Rules

* Prefer to limit line length to 88 characters.
* Leave appropriate space around operators.
* Use appropriate blank lines according to PEP 8 between functions and classes.
* Break long expressions into parentheses.
* Avoid line continuation with backslash.
* Write multiple operations in the same line.
* Avoid using unnecessary semicolons.
* Avoid using `== True` or `== False` in boolean comparisons.
* Use direct truth checking instead of `len(collection) == 0` for empty collection checks.

```python
if not records:
    return []
```

## 14. Pythonic Coding

Prefer Python's standard and readable structures:

* List, dict, and set comprehensions should only be used when they remain readable.
* Complex comprehension expressions should be converted into normal loops.
* `enumerate()` and `zip()` should be used appropriately in suitable contexts.
* Sets should be used instead of lists for membership checks when appropriate.
* Context managers should be used for resource management.
* Manual index tracking should be avoided.
* Mutable default arguments should not be used.

Incorrect:

```python
def add_record(record: Record, records: list[Record] = []) -> None:
    records.append(record)
```

Correct:

```python
def add_record(
    record: Record,
    records: list[Record] | None = None,
) -> list[Record]:
    target_records = records if records is not None else []
    target_records.append(record)
    return target_records
```

## 15. Configuration and Constants

* Embed environment-dependent values directly into the code.
* Manage settings in a centralized configuration layer.
* Avoid the use of magic numbers and magic strings.
* Units should be explicitly stated in variable names or data models.

```python
DEFAULT_TIMEOUT_SECONDS = 30
MAX_RETRY_COUNT = 3
```

## 16. Asynchronous Code

* Use `asyncio` only in real I/O operations.
* Avoid unnecessary use of `async` for CPU-intensive tasks.
* Do not run blocking synchronous I/O inside an async function.
* Explicitly manage task, timeout, and cancellation scenarios.
* Use a semaphore as needed for synchronization control.
* Do not leave background tasks running without tracking them.

## 17. Rules for Editing Existing Code

When making changes to an existing file:

1. First review the existing code and its dependencies.
2. Preserve the project's current architecture and naming conventions.
3. Only modify the necessary sections.
4. Avoid bulk formatting or refactoring in unrelated files.
5. Do not alter the existing API behavior unless necessary.
6. Clearly indicate any backward-incompatible changes.
7. Create a second mechanism that performs the same function.
8. Investigate existing helper functions before adding new code.
9. Reduce code duplication, but avoid excessive abstraction.
10. Run linting, type checking, and tests after making changes.

## 18. Code Generation Process

Follow this order for every coding task:

1. Analyze the request and acceptance criteria.
2. Review the relevant files and current code flow.
3. Determine the smallest safe change plan.
4. Implement clean and PEP 8 compliant code.
5. Remove unnecessary code and imports.
6. Handle error scenarios.
7. Add type hints and required docstrings.
8. Add or update tests.
9. Run formatter, linter, type checker, and tests.
10. Report the changes made in a concise and verifiable manner.

## 19. Output Format

Provide the following information when a task is completed:

### Result

Clearly state whether the task was completed or not.

### Modified Files

Explain the changes made to each file in a sentence.

### Quality Controls

Report the status of the following checks:

* Ruff format
* Ruff lint
* Type check
* Pytest
* Security check

Treat a non-executed check as if it was executed. Clearly state why it could not be executed.

### Important Technical Notes

Only mention issues that require a decision, cause backward incompatibility, or pose a risk.

## 20. Final Decision Rule

Consider the task complete if the code does not meet all of the following criteria:

* No syntax error is present.
* PEP 8 compliant.
* It passes the formatter and lint checks.
* No unused import or dead code is present.
* Type hints are sufficient.
* Errors are handled in a controlled manner.
* Does not contain sensitive information.
* Compatible with the current project architecture.
* Testable.
* Does not contain unnecessary complexity.
* Meets the acceptance criteria of the task.

Priority order:

1. Accuracy
2. Security
3. Data integrity
4. Readability
5. Testability
6. Sustainability
7. Performance
8. Code brevity

Do not compromise accuracy, readability, or security for the sake of a short code.
