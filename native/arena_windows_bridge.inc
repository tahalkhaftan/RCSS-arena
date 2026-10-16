// One Qt process, independently exported top-level windows. No browser clone.
const QString arenaWindows = qEnvironmentVariable("ARENA_WINDOWS_PREVIEW");
const QString arenaDetached = qEnvironmentVariable("ARENA_WINDOWS_DETACHED");
if (!arenaWindows.isEmpty() && !arenaDetached.isEmpty()) {
    auto *timer = new QTimer(this);
    connect(timer, &QTimer::timeout, this,
            [this, arenaWindows, arenaDetached, layoutSlots = QHash<qulonglong,int>(), previous = QByteArray(), oldMode = false]() mutable {
        QFile flag(arenaDetached);bool detached=false;
        if(flag.open(QIODevice::ReadOnly)) detached=flag.readAll().trimmed()=="1";
        // Root-based single-window capture includes native menus. Keep them inside
        // their owning window so a menu at its right/bottom edge is not clipped.
        if(detached)for(auto *popup:QApplication::topLevelWidgets()){
            if(!popup->isVisible()||popup->windowType()!=Qt::Popup||!popup->parentWidget())continue;
            auto *owner=popup->parentWidget()->window();if(owner==popup)continue;
            const QRect rect(owner->mapToGlobal(QPoint(0,0)),owner->size());
            popup->move(qBound(rect.left(),popup->x(),rect.left()+std::max(0,rect.width()-popup->width())),qBound(rect.top(),popup->y(),rect.top()+std::max(0,rect.height()-popup->height())));
        }
        QList<QWidget*> visible;
        for(auto *w:QApplication::topLevelWidgets())
            if(w->isVisible() && w->isWindow() && w->windowType()!=Qt::Popup && w->windowType()!=Qt::ToolTip && !w->windowTitle().isEmpty()) visible.append(w);
        std::sort(visible.begin(),visible.end(),[this](QWidget *a,QWidget *b){if(a==this)return b!=this;if(b==this)return false;return a->winId()<b->winId();});
        QSet<qulonglong> ids;for(auto *w:visible)ids.insert(static_cast<qulonglong>(w->winId()));
        for(auto it=layoutSlots.begin();it!=layoutSlots.end();)if(!ids.contains(it.key()))it=layoutSlots.erase(it);else ++it;
        if(detached!=oldMode){layoutSlots.clear();oldMode=detached;}
        // Execute outside this timer callback: closeEvent may run a modal event loop.
        QFile closeRequest(arenaWindows+".close");
        if(closeRequest.open(QIODevice::ReadOnly)){
            const auto target=closeRequest.readAll().trimmed().toULongLong();closeRequest.close();closeRequest.remove();
            for(auto *w:visible)if(w!=this && static_cast<qulonglong>(w->winId())==target){
                QTimer::singleShot(0,w,[w](){w->close();});break;
            }
        }
        QJsonArray windows;
        for(auto *w:visible){
            const auto id=static_cast<qulonglong>(w->winId());
            auto *owner=w->parentWidget()?w->parentWidget()->window():nullptr;
            const bool attachedDialog=w->isModal() && owner && owner!=w;
            if(detached && attachedDialog){
                layoutSlots.remove(id);
                w->resize(std::min(w->width(),owner->width()),std::min(w->height(),owner->height()));
                const auto origin=owner->mapToGlobal(QPoint(0,0));
                const QPoint desired=origin+QPoint((owner->width()-w->width())/2,(owner->height()-w->height())/2);
                if(w->pos()!=desired)w->move(desired);
            }else if(detached){
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
            item["attached"]=attachedDialog;item["modal"]=w->isModal();item["owner"]=w->parentWidget()?QString::number(static_cast<qulonglong>(w->parentWidget()->window()->winId())):QString();windows.append(item);
        }
        QJsonObject state;state["windows"]=windows;state["detached"]=detached;
        const auto bytes=QJsonDocument(state).toJson(QJsonDocument::Compact);
        if(bytes!=previous){QSaveFile file(arenaWindows);if(file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit())previous=bytes;}
    });
    timer->start(200);
}
