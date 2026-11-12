#!/usr/bin/env python3
"""csr_result.py PROJECT.gprj.user CSR: name the transceivers' register file to the project as the
IDE's SerDes generator does (a "RES.serdes.csr" result file, path relative to the project): the
place and route then gets it (-csr). gw_sh has no command for it: avb.tcl calls this, then opens
the project again."""
import os
import re
import sys

user, csr = sys.argv[1], sys.argv[2]
rel = os.path.relpath(csr, os.path.dirname(user))
entry = '        <ResultFile ResultFileType="RES.serdes.csr" ResultFilePath="%s"/>\n' % rel
if os.path.exists(user):
    s = open(user).read()
    s = re.sub(r'\s*<ResultFile ResultFileType="RES.serdes.csr"[^>]*/>\n?', "\n", s)
    if "<ResultFileList>" in s:
        s = s.replace("<ResultFileList>\n", "<ResultFileList>\n" + entry, 1)
    elif "<ResultFileList/>" in s:
        s = s.replace("<ResultFileList/>", "<ResultFileList>\n" + entry + "    </ResultFileList>", 1)
    else:
        s = s.replace("</UserConfig>", "    <ResultFileList>\n" + entry + "    </ResultFileList>\n</UserConfig>", 1)
else:
    s = ('<?xml version="1" encoding="UTF-8"?>\n<!DOCTYPE ProjectUserData>\n<UserConfig>\n    <Version>1.0</Version>\n'
         '    <ResultFileList>\n' + entry + '    </ResultFileList>\n    <Ui></Ui>\n    <FpUi></FpUi>\n</UserConfig>\n')
open(user, "w").write(s)
