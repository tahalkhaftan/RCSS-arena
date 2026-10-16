// One Qt process, independently exported top-level windows. No browser clone.
const QString arenaWindows = qEnvironmentVariable("ARENA_WINDOWS_PREVIEW");
const QString arenaDetached = qEnvironmentVariable("ARENA_WINDOWS_DETACHED");
if (!arenaWindows.isEmpty() && !arenaDetached.isEmpty()) {
    auto *timer = new QTimer(this);
    connect(timer, &QTimer::timeout, this,
            [this, arenaWindows, arenaDetached, layoutSlots = QHash<qulonglong,int>(), previous = QByteArray(), oldMode = false]() mutable {
        QFile flag(arenaDetached);bool detached=false;
        if(flag.open(QIODevice::ReadOnly)) detached=flag.readAll().trimmed()=="1";
        QList<QWidget*> visible;
        for(auto *w:QApplication::topLevelWidgets())
            if(w->isVisible() && w->isWindow() && w->windowType()!=Qt::Popup && w->windowType()!=Qt::ToolTip && !w->windowTitle().isEmpty()) visible.append(w);
        std::sort(visible.begin(),visible.end(),[this](QWidget *a,QWidget *b){if(a==this)return b!=this;if(b==this)return false;return a->winId()<b->winId();});
        QSet<qulonglong> ids;for(auto *w:visible)ids.insert(static_cast<qulonglong>(w->winId()));
        for(auto it=layoutSlots.begin();it!=layoutSlots.end();)if(!ids.contains(it.key()))it=layoutSlots.erase(it);else ++it;
        if(detached!=oldMode){layoutSlots.clear();oldMode=detached;}
        QJsonArray windows;
        for(auto *w:visible){
            const auto id=static_cast<qulonglong>(w->winId());
            if(detached){
                if(!layoutSlots.contains(id)){
                    int slot=0;while(layoutSlots.values().contains(slot))++slot;
                    if(slot>=9)continue;layoutSlots.insert(id,slot);
                    if(w->isMaximized()||w->isFullScreen())w->showNormal();
                    w->resize(std::min(w->width(),1280),std::min(w->height(),900));
                    w->move((slot%3)*1400+24,(slot/3)*1000+36);
                }
            }else{
                layoutSlots.remove(id);
                const auto point=w->mapToGlobal(QPoint(0,0));
                if(point.x()<0||point.y()<0||point.x()+w->width()>1024||point.y()+w->height()>720){
                    if(w->isMaximized()||w->isFullScreen())w->showNormal();
                    w->resize(std::min(w->width(),1004),std::min(w->height(),660));w->move(w==this?0:10,w==this?0:20);
                }
            }
            const QString cls=QString::fromLatin1(w->metaObject()->className());
            QString key=w==this?"main":cls.contains("FormationEditor")?"formation":cls.contains("DebugMessage")?"debug":"window";
            const auto point=w->mapToGlobal(QPoint(0,0));QJsonObject item;
            item["id"]=QString::number(id);item["title"]=w->windowTitle();item["key"]=key;
            item["width"]=w->width();item["height"]=w->height();item["x"]=point.x();item["y"]=point.y();
            item["modal"]=w->isModal();item["owner"]=w->parentWidget()?QString::number(static_cast<qulonglong>(w->parentWidget()->window()->winId())):QString();windows.append(item);
        }
        QJsonObject state;state["windows"]=windows;state["detached"]=detached;
        const auto bytes=QJsonDocument(state).toJson(QJsonDocument::Compact);
        if(bytes!=previous){QSaveFile file(arenaWindows);if(file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit())previous=bytes;}
    });
    timer->start(200);
}
