#pragma once

#include <QFile>
#include <QJsonDocument>
#include <QString>
#include <QtDebug>

// The glossary's terms (assets/glossary.json, bundled in the resources) as compact JSON text for QML, which parses
// it once per page (JSON.parse) into plain objects: each {term, forms, kind, text, same?}. Plain JS objects, because
// a large nested QVariantList handed to QML tripped the JS heap in debug builds. A missing or broken file gives "[]",
// so steps simply show unmarked.
inline QString loadGlossary(const QString &path = QStringLiteral(":/glossary.json"))
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        qWarning() << "glossary: cannot open" << path;
        return QStringLiteral("[]");
    }
    QJsonParseError error;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !doc.isArray()) {
        qWarning() << "glossary: not a list in" << path << error.errorString();
        return QStringLiteral("[]");
    }
    return QString::fromUtf8(doc.toJson(QJsonDocument::Compact));
}
