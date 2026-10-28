#pragma once
#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QStringList>

#include "api/Api.h"


// The account's diet profile. The server keeps it and applies it to every search, Home and Go on, then; the
// app only says when to leave it out. `enabled` is whether it applies right now: switching it off is for now
// only, so every sign-in (and every save) turns it on again.
class Diet : public QObject
{
    Q_OBJECT

    Q_PROPERTY(QStringList diets READ diets NOTIFY changed)
    Q_PROPERTY(QStringList avoid READ avoid NOTIFY changed)
    Q_PROPERTY(bool hasProfile READ hasProfile NOTIFY changed)
    Q_PROPERTY(bool loaded READ loaded NOTIFY changed)
    Q_PROPERTY(bool saving READ saving NOTIFY changed)
    // Why the last load or save failed; the profile shown stays as it was.
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(bool enabled READ enabled WRITE setEnabled NOTIFY enabledChanged)

public:
    explicit Diet(Api &api, QObject *parent = nullptr);

    QStringList diets() const { return m_diets; }
    QStringList avoid() const { return m_avoid; }
    bool hasProfile() const { return !m_diets.isEmpty() || !m_avoid.isEmpty(); }
    bool loaded() const { return m_loaded; }
    bool saving() const { return m_saving; }
    QString error() const { return m_error; }
    bool enabled() const { return m_enabled; }
    void setEnabled(bool enabled);

    // What a request adds to leave the profile out: "off" while switched off with a profile, empty otherwise.
    QString profileParam() const { return hasProfile() && !m_enabled ? QStringLiteral("off") : QString(); }

    Q_INVOKABLE void load();
    Q_INVOKABLE void save(const QStringList &diets, const QStringList &avoid);
    // The editor opening again: a refusal from its last save is no longer news.
    Q_INVOKABLE void clearError();
    // Signing out: the next person starts with no profile, switched on.
    void clear();

signals:
    void changed();
    void enabledChanged();
    // The server holds a new profile, so what was found with the old one is asked for again.
    void saved();

private:
    void apply(const QJsonObject &data);

    Api &m_api;
    QStringList m_diets;
    QStringList m_avoid;
    bool m_loaded = false;
    bool m_saving = false;
    bool m_enabled = true;
    QString m_error;
    // Bumped by clear(), so an answer meant for the last person is dropped.
    int m_generation = 0;
};
