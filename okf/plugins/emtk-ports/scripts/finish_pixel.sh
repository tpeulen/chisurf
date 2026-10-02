#!/bin/bash
# after capture + compare + deliberate for one imaging pixel plugin: usage finish_pixel.sh <id>
set -e
cd /Users/tpeulen/dev/chisurf
export QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD:/Users/tpeulen/dev/emtk"
PY=/Users/tpeulen/mambaforge/envs/arm64/bin/python
E=okf/plugins/emtk-ports/$1
$PY okf/plugins/emtk-ports/scripts/capture_emtk_after_pixel.py $1 $E 2>&1 | grep -v "WARN\|Syntax\|How spread" | tail -2
$PY -m test.gui.emtk_port_parity compare $1 --out $E > /dev/null 2>&1 || true
$PY okf/plugins/emtk-ports/scripts/deliberate_pixel.py $1 $([ -f $E/extra_deliberate.json ] && echo $E/extra_deliberate.json)
$PY -m test.gui.emtk_port_parity compare $1 --out $E 2>&1 | tail -3
