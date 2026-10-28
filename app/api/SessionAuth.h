// Copied from Pageturner Pageturner/api/SessionAuth.h at ad9342e; comments only.
#pragma once

#include <QByteArray>
#include <QList>
#include <QReadWriteLock>
#include <QString>
#include <QUrl>


// The session token, and the server origins it may be sent to.
//
// Images load on QML's worker threads and pages through PageStore, neither
// through Api, yet both need the token: /media refuses anything without it.
// Each asks here per request. Only the server's own origins (the home address and the
// public one) ever get the token.
class SessionAuth
{
public:
    static SessionAuth &instance();

    void setToken(const QString &token);
    void setOrigins(const QList<QUrl> &bases);

    // The token for a request to one of the server's origins; empty for any
    // other URL, or when signed out.
    QByteArray headerFor(const QUrl &url) const;

    // Same scheme, host and port, with the default port filled in for each.
    static bool sameOrigin(const QUrl &a, const QUrl &b);

private:
    SessionAuth() = default;

    struct Origin
    {
        QString scheme;
        QString host;
        int port = -1;
    };

    static Origin originOf(const QUrl &url);

    mutable QReadWriteLock m_lock;
    QByteArray m_token;
    QList<Origin> m_origins;
};
