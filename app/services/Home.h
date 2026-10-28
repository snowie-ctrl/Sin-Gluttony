#pragma once
#include <QObject>
#include <QString>
#include <QUrlQuery>
#include <QVariantList>
#include <QVariantMap>

#include "api/Api.h"
#include "services/Diet.h"


// Home's data: today's temptation and today's picks (GET /home, in this device's time zone, so the pick holds
// all day), and Go on, then (GET /random). Both follow the diet profile on the server; a change of profile or
// switching it off asks again.
class Home : public QObject
{
    Q_OBJECT

    Q_PROPERTY(QVariantMap pick READ pick NOTIFY changed)
    Q_PROPERTY(bool hasPick READ hasPick NOTIFY changed)
    Q_PROPERTY(QVariantList picks READ picks NOTIFY changed)
    Q_PROPERTY(QString date READ date NOTIFY changed)
    Q_PROPERTY(bool loading READ loading NOTIFY changed)
    // Home has answered once: an empty answer then means nothing fits, not "still asking".
    Q_PROPERTY(bool answered READ answered NOTIFY changed)
    // Why the last load failed; what was shown stays, unless a diet change asked (see the constructor).
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(bool rolling READ rolling NOTIFY rollingChanged)

public:
    explicit Home(Api &api, Diet &diet, QObject *parent = nullptr);

    QVariantMap pick() const { return m_pick; }
    bool hasPick() const { return !m_pick.isEmpty(); }
    QVariantList picks() const { return m_picks; }
    QString date() const { return m_date; }
    bool loading() const { return m_loading; }
    bool answered() const { return m_answered; }
    QString error() const { return m_error; }
    bool rolling() const { return m_rolling; }

    // The IANA zone sent as tz; this device's own unless a test or grab sets another.
    void setTimeZone(const QString &tz) { m_tz = tz; }

    Q_INVOKABLE void load();
    // One recipe that fits the profile; nothing while one is being found.
    Q_INVOKABLE void goOnThen();
    void clear();

signals:
    void changed();
    void rollingChanged();
    void picked(int recipeId);
    void nothingFits();
    void rollFailed(const QString &reason);

private:
    QUrlQuery profileQuery() const;

    Api &m_api;
    Diet &m_diet;
    QString m_tz;
    QVariantMap m_pick;
    QVariantList m_picks;
    QString m_date;
    bool m_loading = false;
    bool m_answered = false;
    QString m_error;
    bool m_rolling = false;
    // Each load supersedes the last; rolls and clear() have their own count, so a load never strands a roll.
    int m_loadGeneration = 0;
    int m_rollGeneration = 0;
};
