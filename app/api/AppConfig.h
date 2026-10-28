// Copied from Pageturner Pageturner/api/AppConfig.h at ad9342e; GLUTTONY_ names.
#pragma once

#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDebug>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QString>
#include <QSysInfo>


// Runtime configuration that must not live in the repository.
//
// The API endpoint is read from a secrets.json that git ignores, so the base
// address can change without touching tracked files. secrets.example.json
// next to it documents the shape.
class AppConfig
{
public:
    static AppConfig &instance()
    {
        static AppConfig config;
        return config;
    }

    QString apiBase() const { return m_apiBase; }
    QString lanApiBase() const { return m_lanApiBase; }
    bool isConfigured() const { return !m_apiBase.isEmpty(); }
    QString configPath() const { return m_loadedFrom; }

    // Stable per-machine id, hashed so the raw machine id never leaves the
    // device. Used to link a device to an account for auto login.
    QString deviceFingerprint() const { return m_fingerprint; }

private:
    AppConfig()
    {
        for (const QString &candidate : searchPaths()) {
            if (candidate.isEmpty() || !QFile::exists(candidate))
                continue;

            QFile file(candidate);
            if (!file.open(QIODevice::ReadOnly))
                continue;

            QJsonParseError error{};
            const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &error);
            if (error.error != QJsonParseError::NoError || !doc.isObject()) {
                qWarning() << "[config]" << candidate << "is not valid JSON:" << error.errorString();
                continue;
            }

            m_apiBase = doc.object().value("apiBase").toString().trimmed();
            while (m_apiBase.endsWith('/'))
                m_apiBase.chop(1);

            // Optional: the server's address on the home network. When it
            // answers, the app talks to it directly instead of the public one.
            m_lanApiBase = doc.object().value("lanApiBase").toString().trimmed();
            while (m_lanApiBase.endsWith('/'))
                m_lanApiBase.chop(1);

            m_loadedFrom = candidate;
            break;
        }

        if (m_apiBase.isEmpty()) {
            qWarning() << "[config] no apiBase found. Copy config/secrets.example.json to "
                          "config/secrets.json and fill it in. Searched:" << searchPaths();
        } else {
            qDebug() << "[config] api base loaded from" << m_loadedFrom;
        }

        m_fingerprint = QString::fromLatin1(
            QCryptographicHash::hash(QSysInfo::machineUniqueId(), QCryptographicHash::Sha256).toHex());
    }

    static QStringList searchPaths()
    {
        QStringList paths;

        // An explicit override always wins, which makes it easy to point a
        // build at a different server without editing anything.
        paths << qEnvironmentVariable("GLUTTONY_SECRETS");

        const QString appDir = QCoreApplication::applicationDirPath();
        paths << appDir + "/config/secrets.json"
              << appDir + "/secrets.json";

#ifdef GLUTTONY_SOURCE_DIR
        // So a dev build finds it without a deploy step.
        paths << QString(GLUTTONY_SOURCE_DIR) + "/config/secrets.json";
#endif
        return paths;
    }

    QString m_apiBase;
    QString m_lanApiBase;
    QString m_loadedFrom;
    QString m_fingerprint;
};
