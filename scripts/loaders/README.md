# scripts/loaders/

Data loading utilities for Excel files and SQL execution.

## Modules

- `sql_loader.py` - Reads and executes .sql files from the sql/ directory
- `excel_loader.py` - Reads ERP Excel exports and normalizes columns

## Usage

```python
from scripts.loaders.sql_loader import execute_sql_file, load_named_queries
from scripts.loaders.excel_loader import read_and_normalize
```
