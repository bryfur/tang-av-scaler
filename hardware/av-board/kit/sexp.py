"""A small reader and writer for KiCad's s-expression files.

parse(text) gives nested lists of str; quoted strings come back as Quoted (a str subclass) so that
they are written back quoted. dump() writes them out again, one list per line where it helps.
"""


class Quoted(str):
    pass


def parse(text):
    stack = [[]]
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "(":
            stack.append([])
            i += 1
        elif c == ")":
            done = stack.pop()
            stack[-1].append(done)
            i += 1
        elif c == '"':
            j = i + 1
            out = []
            while text[j] != '"':
                if text[j] == "\\":
                    out.append({"n": "\n", "t": "\t"}.get(text[j + 1], text[j + 1]))
                    j += 2
                else:
                    out.append(text[j])
                    j += 1
            stack[-1].append(Quoted("".join(out)))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            stack[-1].append(text[i:j])
            i = j
    return stack[0][0]


def q(s):
    return Quoted(s)


def _atom(a):
    if isinstance(a, Quoted):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(a, float):
        s = ("%.4f" % a).rstrip("0").rstrip(".")
        return "0" if s == "-0" else s
    return str(a)


def dump(x, indent=0):
    if not isinstance(x, list):
        return _atom(x)
    flat = "(" + " ".join(dump(e) for e in x) + ")"
    if len(flat) + indent <= 100 and not any(isinstance(e, list) and len(e) > 1 and isinstance(e[1], list) for e in x):
        return flat
    pad = "  " * (indent + 1)
    head = [dump(e) for e in x if not isinstance(e, list)]
    body = [pad + dump(e, indent + 1) for e in x if isinstance(e, list)]
    return "(" + " ".join(head) + ("\n" + "\n".join(body) if body else "") + ")"


def find(x, key):
    """The first child list starting with key."""
    for e in x:
        if isinstance(e, list) and e and e[0] == key:
            return e
    return None


def findall(x, key):
    return [e for e in x if isinstance(e, list) and e and e[0] == key]
