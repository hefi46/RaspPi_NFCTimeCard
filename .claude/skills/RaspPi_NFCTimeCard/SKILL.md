```markdown
# RaspPi_NFCTimeCard Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you the development patterns and conventions used in the `RaspPi_NFCTimeCard` Python project. The repository provides code for managing NFC-based time card functionality on a Raspberry Pi. You'll learn about file naming, import/export styles, commit conventions, and how to structure and run tests in this codebase.

## Coding Conventions

### File Naming
- Use **camelCase** for file names.
  - Example: `nfcReader.py`, `timeCardManager.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .nfcReader import NFCReader
    from .timeCardManager import TimeCardManager
    ```

### Export Style
- Use **named exports** (explicitly list what is exported).
  - Example:
    ```python
    __all__ = ['NFCReader', 'TimeCardManager']
    ```

### Commit Patterns
- Use **conventional commits** with clear prefixes.
- Prefixes detected: `refactor`
- Example commit message:
  ```
  refactor: update time card logic for NFC reader integration
  ```

## Workflows

### Refactoring Code
**Trigger:** When improving code structure or readability without changing external behavior.
**Command:** `/refactor`

1. Identify code that can be improved (e.g., simplify logic, rename variables for clarity).
2. Make changes following the coding conventions.
3. Use a commit message starting with `refactor:`.
   - Example: `refactor: simplify NFC tag reading logic`
4. Run tests to ensure nothing is broken.
5. Push your changes.

## Testing Patterns

- Test files use the pattern: `*.test.*` (e.g., `nfcReader.test.py`)
- Testing framework is **unknown**; check for test runners or scripts in the repository.
- Example test file structure:
  ```python
  import unittest
  from .nfcReader import NFCReader

  class TestNFCReader(unittest.TestCase):
      def test_read_tag(self):
          reader = NFCReader()
          self.assertIsNotNone(reader.read_tag())
  ```
- To run tests, look for instructions in the README or try:
  ```
  python -m unittest discover
  ```

## Commands
| Command    | Purpose                                             |
|------------|-----------------------------------------------------|
| /refactor  | Start a code refactoring workflow                   |
```