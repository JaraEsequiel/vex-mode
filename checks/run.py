"""Run every checks/check_*.py; exit 1 if any reports an error."""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> int:
    root = HERE.parent
    failed = 0
    for module_path in sorted(HERE.glob("check_*.py")):
        module = importlib.import_module(module_path.stem)
        errors = module.run(root)
        status = "ok" if not errors else f"{len(errors)} error(s)"
        print(f"{module_path.stem}: {status}")
        for e in errors:
            print(f"  - {e}")
        failed += len(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
