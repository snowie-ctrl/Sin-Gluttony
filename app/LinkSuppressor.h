// Copied from Pageturner Pageturner/LinkSuppressor.h at ad9342e; GLUTTONY_ names.
#pragma once

#include <QDebug>
#include <QObject>
#include <QUrl>

// For the dev hooks (GLUTTONY_GRAB, GLUTTONY_CLICK): a link a page opens
// is not handed to the owner's browser while a grab is running. Only the
// scheme is logged, never the address.
class LinkSuppressor : public QObject
{
    Q_OBJECT

public slots:
    void suppress(const QUrl &url)
    {
        qInfo().noquote() << "opening" << url.scheme() << "link suppressed during a grab";
    }
};
