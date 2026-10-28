// Copied from Pageturner Pageturner/api/Api.h at ad9342e; pictureUrl replaces mediaUrl.
#pragma once

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QList>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QObject>
#include <QString>
#include <QTimer>
#include <QUrl>
#include <QUrlQuery>
#include <QVariantMap>

#include <functional>


// Thin wrapper over the Gluttony HTTP API.
//
// Every call is asynchronous and hands its result to a callback, so nothing
// on the UI thread ever waits on the network. The reply is parsed as JSON
// once, here, rather than in each caller.
class Api : public QObject
{
    Q_OBJECT

public:
    struct Result
    {
        bool ok = false;            // transport succeeded and status was 2xx
        int httpStatus = 0;
        QJsonObject object;         // object payloads
        QJsonArray array;           // array payloads (a few routes return bare lists)
        QString error;              // transport or server-reported message
    };

    using Handler = std::function<void(const Result &)>;

    explicit Api(QObject *parent = nullptr);

    QString baseUrl() const;
    bool isConfigured() const;

    // Where requests go: the home address when it answers, the public one
    // otherwise. The constructor sets these from secrets.json; tests set them
    // directly.
    void setBases(const QString &lanBase, const QString &publicBase);

    // Runs `ready` once an address is chosen: at once when there is no home
    // address or the choice stands, after the /ping probe otherwise. Offline
    // away from home the choice is made again, so the home address is looked at.
    void whenReady(std::function<void()> ready);

    bool onLan() const { return m_onLan; }

    // Whether the server answers. It goes false when a request cannot reach it
    // (no connection, a timeout) or the tunnel answers for it with its own
    // page because the origin is down, and true on the next answer of any
    // kind. While false, /ping is tried after a while, the wait doubling, and
    // a configured home address is probed beside it (preferred if it answers).
    bool online() const { return m_online; }
    // A failure seen outside Api (PageStore's and Downloads' page fetches),
    // given the URL that failed. It is judged like Api's own failed calls: a
    // failure on the home address never means offline by itself (while using
    // it, the addresses are probed again; once the route has moved to the
    // public address it is ignored); one on the public address does while that
    // is the address in use, and is ignored once the app is on the home one.
    void noteUnreachable(const QUrl &failed);
    // While offline: ping now instead of waiting (the connection screen, tests).
    void checkNow();
    // The first wait before a ping and the longest (15 s and 60 s); tests change them.
    void setPingDelays(int firstMs, int maxMs);
    // The statuses the tunnel answers with its own page when the origin is down.
    static bool originDown(int httpStatus);

    void setSessionToken(const QString &token);
    QString sessionToken() const { return m_sessionToken; }

    void get(const QString &path, const QUrlQuery &query, Handler handler);
    // `transferTimeoutMs` replaces the default 20 s for this one call (0 keeps
    // it): a batch of queued reports is a big body and a slow server's work.
    void post(const QString &path, const QJsonObject &body, Handler handler, int transferTimeoutMs = 0);
    // With a session that is not the app's: a sign-out made offline is told to
    // the server with the token /device/identify hands back, which is never
    // taken on (Session).
    void postAs(const QString &token, const QString &path, const QJsonObject &body, Handler handler);

    // A recipe's picture on the server: kind "thumbs" (400 px) or "images" (1200 px). Requests to it need the
    // session token, which SessionAuth supplies. Empty when unconfigured or for an id that is not one.
    QString pictureUrl(const QString &kind, int recipeId) const;

signals:
    void routeChanged();
    void onlineChanged();
    // The token was set to something else (signed in, out, or a new session):
    // work that waits for one (Downloads) starts again.
    void sessionTokenChanged();

    // A request that carried a session token was refused with 401: the
    // session has ended on the server, so the app should sign out.
    void unauthorised();

private:
    QNetworkRequest buildRequest(const QUrl &url) const;
    void dispatch(QNetworkReply *reply, Handler handler);
    void probe();
    void applyBase(bool lan);
    void noteFailure(QNetworkReply::NetworkError error, const QUrl &url);
    bool isHome(const QUrl &url) const;
    // Whether `url` is on the address requests go to now (m_base).
    bool inUse(const QUrl &url) const;
    void goOffline();
    void noteReached();
    void ping();
    // Offline with the public address in use while a home address is set up.
    bool awayFromHome() const;

    QNetworkAccessManager m_network;
    QString m_sessionToken;
    QString m_fingerprint;

    QString m_lanBase;
    QString m_publicBase;
    QString m_base;
    bool m_onLan = false;
    bool m_chosen = false;
    bool m_probing = false;
    // The probe running was started by a failure, not at start-up: if it ends
    // away from home, the public address is asked at once whether it answers.
    bool m_recheck = false;
    QList<std::function<void()>> m_waiting;
    bool m_online = true;
    QTimer m_pingTimer;
    int m_pingFirst = 15000;
    int m_pingMax = 60000;
    int m_pingDelay = 15000;
};


// Why a call failed, in the server's own words, or that it did not answer. Every
// service that shows a failure to the reader words it through this.
inline QString reasonOf(const Api::Result &result)
{
    if (result.httpStatus == 0)
        return QStringLiteral("Could not reach the server");
    return result.error;
}
