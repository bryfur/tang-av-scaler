"""Which revision a kit tool works on: its first argument, a revision directory (rev-cb; one of the
older ones kept in older/: rev-a, rev-b, rev-ca; or a path to one)."""

import os
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(KIT)


def rev_dir(arg):
    for d in (arg, os.path.join(ROOT, arg), os.path.join(ROOT, "rev-" + arg.lower()), os.path.join(ROOT, "older", arg),
              os.path.join(ROOT, "older", "rev-" + arg.lower())):
        if os.path.isfile(os.path.join(d, "board.py")):
            return os.path.abspath(d)
    raise SystemExit("no revision %r (want rev-cb; or one of older/: rev-a, rev-b, rev-ca)" % arg)


def revisions():
    return sorted(d for top in (ROOT, os.path.join(ROOT, "older")) if os.path.isdir(top)
                  for d in os.listdir(top) if d.startswith("rev-") and os.path.isfile(os.path.join(top, d, "board.py")))


def board(arg):
    """The revision's board.py, imported."""
    d = rev_dir(arg)
    sys.path.insert(0, d)
    sys.path.insert(1, KIT)
    import board as b  # noqa: E402
    return b


def layout(arg):
    """The revision's gen_pcb.py's LAYOUT (its pcbkit.Layout), imported."""
    import importlib.util
    d = rev_dir(arg)
    board(arg)
    spec = importlib.util.spec_from_file_location("gen_pcb", os.path.join(d, "gen_pcb.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.LAYOUT


def args(usage):
    """sys.argv without the revision, after checking one is given."""
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        raise SystemExit(usage + "\nrevisions: " + ", ".join(revisions()))
    return sys.argv[1], sys.argv[2:]
