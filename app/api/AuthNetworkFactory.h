// Copied from Pageturner Pageturner/api/AuthNetworkFactory.h at ad9342e; comments only.
#pragma once

#include <QNetworkAccessManager>
#include <QNetworkRequest>
#include <QQmlNetworkAccessManagerFactory>

#include "api/SessionAuth.h"


// Every Image in QML loads through a manager made here. Requests to the
// server carry the session token, which /media requires; any other
// URL goes out untouched.
class AuthNetworkAccessManager : public QNetworkAccessManager
{
public:
    using QNetworkAccessManager::QNetworkAccessManager;

protected:
    QNetworkReply *createRequest(Operation op, const QNetworkRequest &original,
                                 QIODevice *outgoingData) override
    {
        QNetworkRequest request(original);
        const QByteArray token = SessionAuth::instance().headerFor(request.url());
        if (!token.isEmpty()) {
            request.setRawHeader("X-Session-Token", token);
            // Qt resends custom headers on a redirect, so one to another host
            // would hand it the token; only same-origin redirects are followed.
            request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                                 QNetworkRequest::SameOriginRedirectPolicy);
        }
        return QNetworkAccessManager::createRequest(op, request, outgoingData);
    }
};

class AuthNetworkFactory : public QQmlNetworkAccessManagerFactory
{
public:
    QNetworkAccessManager *create(QObject *parent) override
    {
        return new AuthNetworkAccessManager(parent);
    }
};
