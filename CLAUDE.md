# OmniFocus to Kanban - Development Guide

## Build & Run Commands
- Install dependencies: `pip install -r requirements.txt`
- Run app: `./omnifocustokanban/of-to-kb --kanbanflow` (or `--plane`)
- Evaluation mode: `./omnifocustokanban/of-to-kb --kanbanflow --eval`
- Run single test: `python -m unittest tests/test_filename.py::TestClass::test_method`

## Code Style Guidelines
- Type hints required for function parameters and return values
- Use dataclasses for structured data (e.g., Task class)
- Exception handling: catch specific exceptions with informative error messages
- Logging: use the module-level logger with appropriate levels (debug/info/warning/error)
- Constants defined at module level in UPPER_CASE
- SQL queries defined as module-level constants
- Class methods that don't use instance variables should be @staticmethod
- Follow PEP 8 for naming: snake_case for functions/variables, CamelCase for classes

## Error Handling Pattern
Try specific operations individually with appropriate error messages. Use the format:
```python
try:
    # operation
except SpecificException as e:
    logging.error(f"Meaningful error message: {e}")
    # handle or raise
```