"""Apply only the optional, environment-gated bridge to pinned upstream Qt."""
import sys,shutil
from pathlib import Path
root=Path(sys.argv[1]);source=root/'src/qt/formation_editor_window.cpp'
s=source.read_text();anchor='    addToolBarActions();'
if s.count(anchor)!=1:raise SystemExit('Upstream formation constructor changed')
s=s.replace('#include <QtGlobal>','#include <QtGlobal>\n#include <QTimer>\n#include <QSaveFile>\n#include <QJsonDocument>\n#include <QJsonObject>\n#include <QJsonArray>')
s=s.replace(anchor,anchor+'\n#include "arena_formation_bridge.inc"')
source.write_text(s);shutil.copyfile(Path(__file__).parent.parent/'native/arena_formation_bridge.inc',source.parent/'arena_formation_bridge.inc')
