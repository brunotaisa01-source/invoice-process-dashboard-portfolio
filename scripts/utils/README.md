# scripts/utils/

Shared utility scripts.

## Modules

- `archive_manager.py` - Moves processed Excel files to data/archive/YYYY/MM/

## Usage

```bash
python -m scripts.utils.archive_manager           # Archive processed files
python -m scripts.utils.archive_manager --dry-run  # Preview without moving
```
