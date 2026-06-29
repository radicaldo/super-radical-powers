#!/usr/bin/env python3
import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # make `offload` and `tests` importable

def main(argv):
    loader = unittest.TestLoader()
    if len(argv) > 1:
        names = [m if m.startswith("tests.") else f"tests.{m}" for m in argv[1:]]
        suite = loader.loadTestsFromNames(names)
    else:
        suite = loader.discover(start_dir=os.path.join(HERE, "tests"), top_level_dir=HERE)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
