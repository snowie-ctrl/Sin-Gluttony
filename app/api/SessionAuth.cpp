// Copied from Pageturner Pageturner/api/SessionAuth.cpp at ad9342e; comments only.
#include "api/SessionAuth.h"

SessionAuth &SessionAuth::instance()
{
    static SessionAuth auth;
    return auth;
}

void SessionAuth::setToken(const QString &token)
{
    QWriteLocker locker(&m_lock);
    m_token = token.toUtf8();
}

void SessionAuth::setOrigins(const QList<QUrl> &bases)
{
    QList<Origin> origins;
    for (const QUrl &base : bases)
        if (base.isValid() && !base.host().isEmpty())
            origins.append(originOf(base));

    QWriteLocker locker(&m_lock);
    m_origins = origins;
}

QByteArray SessionAuth::headerFor(const QUrl &url) const
{
    const Origin wanted = originOf(url);

    QReadLocker locker(&m_lock);
    if (m_token.isEmpty())
        return {};
    for (const Origin &origin : m_origins)
        if (origin.scheme == wanted.scheme && origin.host == wanted.host && origin.port == wanted.port)
            return m_token;
    return {};
}

bool SessionAuth::sameOrigin(const QUrl &a, const QUrl &b)
{
    const Origin x = originOf(a);
    const Origin y = originOf(b);
    return x.scheme == y.scheme && x.host == y.host && x.port == y.port;
}

SessionAuth::Origin SessionAuth::originOf(const QUrl &url)
{
    const QString scheme = url.scheme().toLower();
    return {scheme, url.host().toLower(), url.port(scheme == QLatin1String("https") ? 443 : 80)};
}
