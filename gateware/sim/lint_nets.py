#!/usr/bin/env python3
"""lint_nets.py [FILE.v ...]: names that a module connects to an instance's port, or assigns, without
declaring them.  Verilog makes such a name a one-bit wire, driven by nothing where it is read, and the
tools build it so without a word (2026-11-15: the pass-through's store was never written: 720p green).
Run before a build (default: every file in rtl/); it lists them and fails if there are any.
(A plain reading of the text, not a parser: comments and strings left out, generate blocks' own
declarations counted as the module's.)"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = set("""always assign begin end if else case endcase default for while posedge negedge or and not
generate endgenerate genvar integer wire reg input output inout parameter localparam function endfunction
task endtask initial module endmodule signed unsigned""".split())
DECL = re.compile(r"\b(input|output|inout|wire|reg|integer|genvar|parameter|localparam|real|time)\b([^;]*);", re.S)
PORTS = re.compile(r"\.\s*\w+\s*\(\s*([A-Za-z_]\w*)\s*[\[\)]")
ASSIGN = re.compile(r"\bassign\s+([A-Za-z_]\w*)")


def strip(t):
    t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)
    t = re.sub(r"//[^\n]*", " ", t)
    return re.sub(r'"[^"\n]*"', '""', t)


def names(decl):
    d = re.sub(r"\[[^\]]*\]", " ", decl)            # (ranges)
    d = re.sub(r"=[^,;]*", " ", d)                    # (values)
    d = re.sub(r"\b(signed|unsigned|wire|reg|integer)\b", " ", d)
    return set(re.findall(r"[A-Za-z_]\w*", d)) - KEY


def check(path):
    t = strip(open(path).read())
    bad = []
    for m in re.finditer(r"\bmodule\s+(\w+)(.*?)\bendmodule\b", t, re.S):
        name, body = m.group(1), m.group(2)
        decl = set()
        for d in DECL.finditer(body):
            decl |= names(d.group(2))
        # (a module's ports in its header: "input [7:0] a, b," and the old style's names)
        head = body.split(";", 1)[0]
        for d in re.finditer(r"\b(input|output|inout)\b([^;)]*?)(?=\b(?:input|output|inout)\b|\)\s*$|$)", head, re.S):
            decl |= names(d.group(2))
        decl |= set(re.findall(r"\bfunction\b[^;]*?\b(\w+)\s*\(", body))
        decl |= set(re.findall(r"\bfunction\b(?:\s*\[[^\]]*\])?\s*(\w+)", body))
        # (instances' own names, and the generate blocks' labels, are not nets)
        # (a parameter's value given to an instance, #(.P(X)), is not a net: those lists left out)
        nets_body = re.sub(r"#\s*\((?:[^()]|\([^()]*(?:\([^()]*\)[^()]*)*\))*\)", " ", body)
        used = [(u, "port") for u in PORTS.findall(nets_body)] + [(u, "assign") for u in ASSIGN.findall(nets_body)]
        for u, how in used:
            if u not in decl and u not in KEY and not u.startswith("`"):
                bad.append((os.path.basename(path), name, u, how))
    return bad


def main():
    files = sys.argv[1:] or sorted(os.path.join(HERE, "../rtl", f) for f in os.listdir(os.path.join(HERE, "../rtl")) if f.endswith(".v"))
    bad = sorted(set(b for f in files for b in check(f)))
    for f, mod, u, how in bad:
        print("%s: module %s: %s (%s) is not declared" % (f, mod, u, how))
    print("%d names used without a declaration" % len(bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
