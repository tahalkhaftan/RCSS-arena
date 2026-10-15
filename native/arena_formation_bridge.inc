// Optional Arena bridge. Runs on Qt's GUI thread; leaves native editing algorithms intact.
const QString arenaPreview = qEnvironmentVariable("ARENA_FORMATION_PREVIEW");
const QString arenaCommand = qEnvironmentVariable("ARENA_FORMATION_COMMAND");
if (!arenaPreview.isEmpty() && !arenaCommand.isEmpty()) {
    auto *arenaTimer = new QTimer(this);
    connect(arenaTimer, &QTimer::timeout, this,
            [this, arenaPreview, arenaCommand, previous = QByteArray()]() mutable {
        const auto writeJson = [](const QString &path, const QJsonObject &value) {
            QSaveFile file(path);
            const QByteArray bytes = QJsonDocument(value).toJson(QJsonDocument::Compact);
            return file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit();
        };
        QFile commandFile(arenaCommand);
        if (commandFile.exists() && commandFile.open(QIODevice::ReadOnly)) {
            const auto cmd = QJsonDocument::fromJson(commandFile.readAll()).object();
            commandFile.close();QFile::remove(arenaCommand);
            QJsonObject reply;reply["id"] = cmd["id"];reply["ok"] = false;
            const QString action = cmd["action"].toString();
            auto data = M_main_data.formationEditData();
            if (action == "open") {
                if (data && data->isModified()) reply["error"] = "Export the unsaved formation before opening another file.";
                else {auto probe=std::make_shared<FormationEditData>();if(!probe->openConf(cmd["path"].toString().toStdString())) reply["error"]="Invalid formation file.";else {reply["ok"] = openConfFile(cmd["path"].toString());if(reply["ok"].toBool()) {show();raise();}}}
            } else if (action == "new") {
                if (data && data->isModified()) reply["error"] = "Export the unsaved formation before creating another one.";
                else {
                    auto fresh = std::make_shared<FormationEditData>();
                    if (fresh->newFormation(rcsc::FormationDT::NAME)) {
                        M_main_data.setFormationEditData(fresh);M_tree_view->clear();
                        M_index_spin_box->setEnabled(true);M_input_panel->setEnabled(true);M_tree_view->setEnabled(true);
                        M_index_spin_box->setRange(0,static_cast<int>(fresh->formationData()->dataCont().size()));
                        updatePanel();M_tree_view->updateData();show();raise();emit editorUpdated();reply["ok"]=true;
                    }
                }
            } else if (action == "export" && data && data->formation() && data->formationData()) {
                // Commit exactly the layout currently shown in the editor into its native model.
                int index = -1;
                const auto ball = data->currentState().ball_;
                for (size_t i=0;i<data->formationData()->dataCont().size();++i) {
                    const auto *sample=data->formationData()->data(i);
                    if(sample && sample->ball_.dist2(ball)<1.0e-8) {index=static_cast<int>(i);break;}
                }
                if(data->formation()->methodName()=="Static" && !data->formationData()->dataCont().empty()) index=0;
                const std::string error = index>=0 ? data->replaceData(index) : data->addData();
                if (!error.empty()) reply["error"]=QString::fromStdString(error);
                else {
                    for(size_t i=0;i<data->formationData()->dataCont().size();++i) {const auto *sample=data->formationData()->data(i);if(sample && sample->ball_.dist2(ball)<1.0e-8) {data->setCurrentIndex(static_cast<int>(i));M_index_spin_box->setValue(static_cast<int>(i+1));break;}}
                    reply["ok"]=data->saveConfAs(cmd["path"].toString().toStdString());
                    updatePanel();M_tree_view->updateData();emit editorUpdated();
                }
            } else reply["error"] = "Create or open a formation first.";
            if(!reply["ok"].toBool() && !reply.contains("error")) reply["error"]="The native editor could not complete the operation.";
            writeJson(arenaCommand+".reply",reply);
        }
        const auto data = M_main_data.formationEditData();
        QJsonObject snapshot;snapshot["available"]=bool(data && data->formation());
        if (data && data->formation()) {
            const auto &state=data->currentState();QJsonArray players;
            for(size_t i=0;i<state.players_.size();++i) {
                QJsonObject player;player["number"]=static_cast<int>(i+1);
                player["x"]=state.players_[i].x;player["y"]=state.players_[i].y;
                player["role"]=QString::fromStdString(data->formation()->roleName(static_cast<int>(i+1)));
                players.append(player);
            }
            snapshot["players"]=players;snapshot["ball"]=QJsonArray{state.ball_.x,state.ball_.y};
            snapshot["modified"]=data->isModified();snapshot["sample_index"]=data->currentIndex();
            snapshot["samples"]=static_cast<int>(data->formationData()->dataCont().size());
            snapshot["file"]=QFileInfo(QString::fromStdString(data->filePath())).fileName();
        }
        const auto bytes=QJsonDocument(snapshot).toJson(QJsonDocument::Compact);
        if(bytes!=previous && writeJson(arenaPreview,snapshot)) previous=bytes;
    });
    arenaTimer->start(600);
}
