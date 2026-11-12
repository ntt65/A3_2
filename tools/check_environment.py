"""Report the runtime and check that the project dependencies can be imported."""

import platform
import sys


def main() -> int:
    print(f"Python: {platform.python_version()}")
    print(f"Platform: {platform.platform()}")

    try:
        import cv2
        import numpy
    except (ImportError, OSError) as error:
        print(f"Dependency import failed: {error}", file=sys.stderr)
        return 1

    print(f"OpenCV: {cv2.__version__}")
    print(f"NumPy: {numpy.__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
