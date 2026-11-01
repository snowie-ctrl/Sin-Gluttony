// The account half of Pageturner Pageturner/services/AccountStore.cpp at ad9342e: open, close, wipe, the
// pending sign-out and last.json as there; an offline start needs a saved recipe instead of a download;
// wiped names the account whose folder was deleted.
#include "services/AccountStore.h"

#include <QDebug>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QSaveFile>


AccountStore::AccountStore(const QString &root, QObject *parent) : QObject(parent), m_root(root)
{
    const int pending = readJson(accountsDir() + QStringLiteral("/pending-logout.json")).value("uid").toInt();
    m_pendingLogout = pending > 0 ? pending : -1;
}

QString AccountStore::accountsDir() const
{
    return m_root + QStringLiteral("/accounts");
}

QString AccountStore::dir() const
{
    return m_uid > 0 ? accountsDir() + QStringLiteral("/%1").arg(m_uid) : QString();
}

QString AccountStore::file(const QString &name) const
{
    return m_uid > 0 ? dir() + QLatin1Char('/') + name : QString();
}

QString AccountStore::recipesDir() const
{
    return m_uid > 0 ? dir() + QStringLiteral("/recipes") : QString();
}

QString AccountStore::recipeFile(int recipeId) const
{
    return m_uid > 0 && recipeId > 0 ? recipesDir() + QStringLiteral("/%1.json").arg(recipeId) : QString();
}

void AccountStore::open(int uid, const QString &username)
{
    if (uid <= 0)
        return;
    const bool another = uid != m_uid;
    m_uid = uid;
    QDir().mkpath(recipesDir());
    writeJson(file(QStringLiteral("account.json")), QJsonObject{{"UID", uid}, {"username", username}});
    writeJson(accountsDir() + QStringLiteral("/last.json"), QJsonObject{{"UID", uid}});
    if (another)
        emit changed();
}

void AccountStore::close()
{
    if (m_uid <= 0)
        return;
    m_uid = -1;
    emit changed();
}

void AccountStore::wipe()
{
    if (m_uid <= 0)
        return;
    const int uid = m_uid;
    m_uid = -1;
    emit changed();
    removeAccount(uid);
}

void AccountStore::wipeAccount(int uid)
{
    if (uid <= 0)
        return;
    if (uid == m_uid) {
        wipe();
        return;
    }
    removeAccount(uid);
}

void AccountStore::removeAccount(int uid)
{
    emit wiped(uid);
    const QString folder = accountsDir() + QStringLiteral("/%1").arg(uid);
    // Nothing names the account any more before its files go, so a wipe cut short never opens offline later.
    const QString last = accountsDir() + QStringLiteral("/last.json");
    if (readJson(last).value("UID").toInt() == uid)
        QFile::remove(last);
    // Windows refuses to delete a file that is open; the rest still goes and the sign-out still completes.
    if (!QDir(folder).removeRecursively())
        qWarning() << "[accounts] could not delete everything of account" << uid
                   << "(a file was in use); what is left stays in" << folder;
}

void AccountStore::setPendingLogout(int uid)
{
    if (uid <= 0)
        return;
    m_pendingLogout = uid;
    writeJson(accountsDir() + QStringLiteral("/pending-logout.json"), QJsonObject{{"uid", uid}});
}

void AccountStore::clearPendingLogout()
{
    m_pendingLogout = -1;
    QFile::remove(accountsDir() + QStringLiteral("/pending-logout.json"));
}

void AccountStore::forgetLast()
{
    QFile::remove(accountsDir() + QStringLiteral("/last.json"));
}

QVariantMap AccountStore::offlineAccount() const
{
    const int uid = readJson(accountsDir() + QStringLiteral("/last.json")).value("UID").toInt();
    if (uid <= 0)
        return {};
    const QString folder = accountsDir() + QStringLiteral("/%1").arg(uid);
    const QJsonObject account = readJson(folder + QStringLiteral("/account.json"));
    if (account.value("UID").toInt() != uid)
        return {};
    // Only a saved recipe makes an offline start worth anything.
    if (QDir(folder + QStringLiteral("/recipes")).entryList({QStringLiteral("*.json")}, QDir::Files).isEmpty())
        return {};
    return {{"UID", uid}, {"username", account.value("username").toString()}};
}

bool AccountStore::writeJson(const QString &path, const QJsonObject &object)
{
    if (path.isEmpty())
        return false;
    QDir().mkpath(QFileInfo(path).absolutePath());
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly))
        return false;
    file.write(QJsonDocument(object).toJson(QJsonDocument::Compact));
    return file.commit();
}

QJsonObject AccountStore::readJson(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return QJsonDocument::fromJson(file.readAll()).object();
}
