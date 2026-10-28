// Copied from Pageturner Pageturner/api/Api.cpp at ad9342e; pictureUrl replaces mediaUrl.
// It also differs from Showtime in giving every request a 20 s transfer timeout.
#include "api/Api.h"
#include "api/AppConfig.h"
#include "api/SessionAuth.h"

#include <QJsonArray>
#include <QJsonParseError>
#include <QNetworkReply>
#include <QUrl>

#include <utility>


Api::Api(QObject *parent)
    : QObject(parent)
    , m_fingerprint(AppConfig::instance().deviceFingerprint())
{
    m_network.setAutoDeleteReplies(false);
    // A server that accepts a request and never answers would otherwise leave
    // its caller (a chapter's spinner, say) waiting for ever; this ends it in
    // the normal error path. The LAN probe sets its own, shorter one.
    m_network.setTransferTimeout(20000);
    setBases(AppConfig::instance().lanApiBase(), AppConfig::instance().apiBase());
    m_pingTimer.setSingleShot(true);
    connect(&m_pingTimer, &QTimer::timeout, this, &Api::ping);
}

QString Api::baseUrl() const
{
    return m_base;
}

bool Api::isConfigured() const
{
    return !m_base.isEmpty();
}

void Api::setBases(const QString &lanBase, const QString &publicBase)
{
    m_lanBase = lanBase;
    m_publicBase = publicBase;
    m_chosen = lanBase.isEmpty();
    m_onLan = false;
    m_base = publicBase;

    QList<QUrl> origins;
    for (const QString &base : {lanBase, publicBase})
        if (!base.isEmpty())
            origins.append(QUrl(base));
    SessionAuth::instance().setOrigins(origins);
}

void Api::whenReady(std::function<void()> ready)
{
    // Offline on the public address, the home address may be what came back:
    // signing in (the connection screen's Retry) looks there first.
    if (awayFromHome())
        m_chosen = false;
    if (m_chosen) {
        if (ready)
            ready();
        return;
    }
    m_waiting.append(std::move(ready));
    probe();
}

void Api::probe()
{
    if (m_probing || m_lanBase.isEmpty())
        return;
    m_probing = true;

    // Short on purpose: away from home the address either refuses at once or
    // never answers, and sign-in waits for this.
    QNetworkRequest request(QUrl(m_lanBase + "/ping"));
    request.setTransferTimeout(1500);
    QNetworkReply *reply = m_network.get(request);

    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        // A reply that never connected has nothing to read (and says so).
        const bool answered = reply->error() == QNetworkReply::NoError;
        const QJsonObject body = answered ? QJsonDocument::fromJson(reply->readAll()).object() : QJsonObject();
        const bool home = answered
                          && reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt() == 200
                          && body.value("status").toString() == QLatin1String("ok");
        reply->deleteLater();

        m_probing = false;
        m_chosen = true;
        applyBase(home);
        // The probe reads its own reply, never through dispatch, so an answer
        // from home has to bring the app back here (offline, it is how the
        // home server coming back is noticed).
        if (home)
            noteReached();

        // A failure sent us looking and the home address is gone: the public
        // one may be gone too (the server itself down, the commonest outage at
        // home). Asking it through get() lets dispatch decide, so the app goes
        // offline and starts pinging instead of claiming to be online until
        // some later call fails.
        if (std::exchange(m_recheck, false) && !home)
            get(QStringLiteral("/ping"), QUrlQuery(), nullptr);

        const QList<std::function<void()>> waiting = std::exchange(m_waiting, {});
        for (const auto &ready : waiting)
            if (ready)
                ready();
    });
}

void Api::applyBase(bool lan)
{
    const bool changed = lan != m_onLan;
    m_onLan = lan;
    m_base = lan ? m_lanBase : m_publicBase;
    if (changed)
        emit routeChanged();
}

void Api::noteFailure(QNetworkReply::NetworkError error, const QUrl &url)
{
    // Only the home address going quiet is worth a second look; an HTTP error
    // is the server answering, which is not a reason to switch. Compared by
    // origin, not by text, so a differently written but identical address
    // (case, an explicit default port) still counts as the home address.
    if (!m_onLan || !SessionAuth::sameOrigin(url, QUrl(m_lanBase)))
        return;

    switch (error) {
    case QNetworkReply::ConnectionRefusedError:
    case QNetworkReply::RemoteHostClosedError:
    case QNetworkReply::HostNotFoundError:
    case QNetworkReply::TimeoutError:
    case QNetworkReply::OperationCanceledError:
    case QNetworkReply::TemporaryNetworkFailureError:
    case QNetworkReply::NetworkSessionFailedError:
    case QNetworkReply::UnknownNetworkError:
        break;
    default:
        return;
    }
    m_chosen = false;
    m_recheck = true;
    probe();
}

void Api::setSessionToken(const QString &token)
{
    const bool changed = token != m_sessionToken;
    m_sessionToken = token;

    // Images and video read it from there; they never pass through Api.
    SessionAuth::instance().setToken(token);
    if (changed)
        emit sessionTokenChanged();
}

QNetworkRequest Api::buildRequest(const QUrl &url) const
{
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    // The token goes on every request, so a redirect must never carry it to
    // another host; same-origin is also stricter than "no less safe".
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                         QNetworkRequest::SameOriginRedirectPolicy);

    // Every route except sign-in and the reachability check needs the session
    // token, so it is sent on every call.
    if (!m_sessionToken.isEmpty())
        request.setRawHeader("X-Session-Token", m_sessionToken.toUtf8());
    if (!m_fingerprint.isEmpty())
        request.setRawHeader("X-Device-Fingerprint", m_fingerprint.toUtf8());

    return request;
}

void Api::dispatch(QNetworkReply *reply, Handler handler)
{
    connect(reply, &QNetworkReply::finished, this, [this, reply, handler]() {
        Result result;
        result.httpStatus = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();

        const QByteArray payload = reply->readAll();
        const bool transportFailed = reply->error() != QNetworkReply::NoError && payload.isEmpty();

        QJsonParseError parseError{};
        const QJsonDocument doc = transportFailed ? QJsonDocument() : QJsonDocument::fromJson(payload, &parseError);
        if (doc.isObject())
            result.object = doc.object();
        else if (doc.isArray())
            result.array = doc.array();

        // Only a request that was signed in can find its session gone; a 401
        // to sign-in itself is a wrong password, not an ended session. A
        // signed-in 401 naming invalid_credentials is a refusal too (a wrong
        // current password on /user/password): signing out over a typo would
        // throw the reader back to the sign-in page.
        if (result.httpStatus == 401 && reply->request().hasRawHeader("X-Session-Token")
            && result.object.value("status").toString() != QLatin1String("invalid_credentials"))
            emit unauthorised();

        if (transportFailed) {
            noteFailure(reply->error(), reply->url());
            // Qt's text for an HTTP error names the whole address, host
            // included, and it reaches the reader's screen; a server that
            // answered with no body is named by its status instead.
            result.error = result.httpStatus ? QStringLiteral("HTTP %1").arg(result.httpStatus)
                                             : reply->errorString();
        } else if (parseError.error != QJsonParseError::NoError) {
            result.error = QStringLiteral("bad JSON from server: %1").arg(parseError.errorString());
        } else {
            // Routes signal failure two ways: an HTTP status, or a status field in
            // an otherwise fine 200. Treat both as failure so callers only check
            // one thing.
            //
            // Failure is what is named, not success. Routes describe what they did
            // ("created", "updated", "ignored", "new_session"), and a list of
            // accepted words rejected every one of those: progress reports were
            // written on the server yet always read as failed here. Every failing
            // route already sends a 4xx or 5xx, and "error" is the one word used
            // for failure in a body, so those are the only two things checked.
            const QString reported = result.object.value("status").toString();
            const bool statusOk = result.httpStatus >= 200 && result.httpStatus < 300;
            const bool bodyOk = reported != QLatin1String("error");

            result.ok = statusOk && bodyOk;
            if (!result.ok) {
                result.error = result.object.value("message").toString();
                if (result.error.isEmpty())
                    result.error = reported.isEmpty()
                                       ? QStringLiteral("HTTP %1").arg(result.httpStatus)
                                       : reported;
            }
        }

        // Nothing answered, or the tunnel answered for a server that is down:
        // offline. A JSON error is the server answering, however unhappily.
        const bool parsed = doc.isObject() || doc.isArray();
        const bool unreachable = (transportFailed && result.httpStatus == 0)
                                 || (!parsed && originDown(result.httpStatus));
        if (!unreachable)
            noteReached();
        else if (!isHome(reply->url()) && inUse(reply->url()))
            // A failure on the home address is never decided here: while using
            // it noteFailure above sends the probe to look again, and after the
            // route has moved (a request that hung until its timeout once the
            // reader had left home) the public address is what counts. The
            // mirror of that: a public request still out when the app came back
            // on the home server (the ping sent beside the home probe, answered
            // by the tunnel after home did) says nothing about the route now.
            goOffline();

        reply->deleteLater();
        if (handler)
            handler(result);
    });
}

void Api::get(const QString &path, const QUrlQuery &query, Handler handler)
{
    if (!isConfigured()) {
        Result result;
        result.error = QStringLiteral("no API endpoint configured");
        if (handler)
            handler(result);
        return;
    }

    QUrl url(baseUrl() + path);
    if (!query.isEmpty())
        url.setQuery(query);

    dispatch(m_network.get(buildRequest(url)), std::move(handler));
}

void Api::post(const QString &path, const QJsonObject &body, Handler handler, int transferTimeoutMs)
{
    if (!isConfigured()) {
        Result result;
        result.error = QStringLiteral("no API endpoint configured");
        if (handler)
            handler(result);
        return;
    }

    const QUrl url(baseUrl() + path);
    QNetworkRequest request = buildRequest(url);
    if (transferTimeoutMs > 0)
        request.setTransferTimeout(transferTimeoutMs);
    dispatch(m_network.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact)), std::move(handler));
}

void Api::postAs(const QString &token, const QString &path, const QJsonObject &body, Handler handler)
{
    if (!isConfigured()) {
        Result result;
        result.error = QStringLiteral("no API endpoint configured");
        if (handler)
            handler(result);
        return;
    }

    QNetworkRequest request = buildRequest(QUrl(baseUrl() + path));
    request.setRawHeader("X-Session-Token", token.toUtf8());
    dispatch(m_network.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact)), std::move(handler));
}

QString Api::pictureUrl(const QString &kind, int recipeId) const
{
    if (!isConfigured() || recipeId <= 0)
        return {};
    return baseUrl() + QLatin1Char('/') + kind + QLatin1Char('/') + QString::number(recipeId);
}

bool Api::originDown(int httpStatus)
{
    return httpStatus == 502 || httpStatus == 521 || httpStatus == 522 || httpStatus == 523
           || httpStatus == 530;
}

void Api::setPingDelays(int firstMs, int maxMs)
{
    m_pingFirst = firstMs;
    m_pingMax = qMax(firstMs, maxMs);
    m_pingDelay = firstMs;
}

void Api::noteUnreachable(const QUrl &failed)
{
    // The same rule as for Api's own calls, minus the error kind (a page fetch
    // reports only the address): the home address going quiet is a reason to
    // look again, never to call the app offline.
    if (isHome(failed)) {
        // Only while it is the route in use, and not while a probe is already
        // running; after the route has moved there is nothing left to check.
        if (m_onLan && m_chosen) {
            m_chosen = false;
            m_recheck = true;
            probe();
        }
        return;
    }
    // Anywhere else, only the address in use decides (as in dispatch).
    if (inUse(failed))
        goOffline();
}

bool Api::isHome(const QUrl &url) const
{
    return !m_lanBase.isEmpty() && SessionAuth::sameOrigin(url, QUrl(m_lanBase));
}

bool Api::inUse(const QUrl &url) const
{
    return SessionAuth::sameOrigin(url, QUrl(m_base));
}

void Api::goOffline()
{
    if (!m_online)
        return;
    m_online = false;
    m_pingDelay = m_pingFirst;
    m_pingTimer.start(m_pingDelay);
    emit onlineChanged();
}

void Api::noteReached()
{
    if (m_online)
        return;
    m_online = true;
    m_pingTimer.stop();
    emit onlineChanged();
}

void Api::checkNow()
{
    if (m_online)
        return;
    m_pingTimer.stop();
    ping();
}

bool Api::awayFromHome() const
{
    return !m_online && !m_lanBase.isEmpty() && !m_onLan;
}

void Api::ping()
{
    if (m_online)
        return;
    // Once offline the route is the public address, and pinging only that
    // would miss the home server coming back without the tunnel (and keep a
    // session that went through an outage at home on the tunnel for good).
    // The home address is probed beside it; whichever answers brings the app
    // back, on that address, and an answer from home wins (applyBase).
    if (awayFromHome() && !m_probing) {
        m_chosen = false;
        probe();
    }
    get(QStringLiteral("/ping"), QUrlQuery(), [this](const Result &) {
        // Any answer has already brought the app back (dispatch); only
        // silence waits, longer each time, for the next try.
        if (m_online)
            return;
        m_pingDelay = qMin(m_pingDelay * 2, m_pingMax);
        m_pingTimer.start(m_pingDelay);
    });
}
