"""Which revision a kit tool works on: its first argument, a revision directory (rev-a, rev-b, or a
path to one)."""

import os
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(KIT)


def rev_dir(arg):
    for d in (arg, os.path.join(ROOT, arg), os.path.join(ROOT, "rev-" + arg.lower())):
        if os.path.isfile(os.path.join(d, "board.py")):
            return os.path.abspath(d)
    raise SystemExit("no revision %r (want rev-a, rev-b, ...)" % arg)


def revisions():
    return sorted(d for d in os.listdir(ROOT) if d.startswith("rev-") and os.path.isfile(os.path.join(ROOT, d, "board.py")))


def board(arg):
    """The revision's board.py, imported."""
    d = rev_dir(arg)
    sys.path.insert(0, d)
    sys.path.insert(1, KIT)
    import board as b  # noqa: E402
    return b


def args(usage):
    """sys.argv without the revision, after checking one is given."""
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        raise SystemExit(usage + "\nrevisions: " + ", ".join(revisions()))
    return sys.argv[1], sys.argv[2:]
