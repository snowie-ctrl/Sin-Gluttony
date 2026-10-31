#include "services/SyncQueue.h"

#include <QDateTime>
#include <QJsonArray>
#include <QUuid>

#include "services/AccountStore.h"


SyncQueue::SyncQueue(Api &api, QObject *parent) : QObject(parent), m_api(api)
{
    m_retry.setSingleShot(true);
    m_retry.setInterval(15000);
    connect(&m_retry, &QTimer::timeout, this, &SyncQueue::flush);
    // Spec §6: sent on reconnect; a sign-in is the token arriving.
    connect(&m_api, &Api::onlineChanged, this, &SyncQueue::flush);
    connect(&m_api, &Api::sessionTokenChanged, this, &SyncQueue::flush);
}

bool SyncQueue::offline() const
{
    return !m_api.online() || m_api.sessionToken().isEmpty();
}

void SyncQueue::setStore(AccountStore *store)
{
    m_store = store;
    connect(store, &AccountStore::changed, this, &SyncQueue::load);
    load();
}

void SyncQueue::load()
{
    // Another account, or none: anything on its way belonged to the last one, whose file keeps it.
    ++m_epoch;
    m_sending.clear();
    m_refusedNow.clear();
    m_retry.stop();
    m_file = m_store ? m_store->file(QStringLiteral("sync-queue.json")) : QString();
    m_changes.clear();
    if (!m_file.isEmpty())
        for (const QJsonValue &value : AccountStore::readJson(m_file).value("changes").toArray())
            m_changes << value.toObject();
    emit changed();
    flush();
}

void SyncQueue::save()
{
    if (m_file.isEmpty())
        return;
    QJsonArray changes;
    for (const QJsonObject &change : m_changes)
        changes.append(change);
    AccountStore::writeJson(m_file, QJsonObject{{"changes", changes}});
}

int SyncQueue::indexOf(const QString &id) const
{
    for (int i = 0; i < m_changes.size(); ++i)
        if (m_changes.at(i).value("id").toString() == id)
            return i;
    return -1;
}

QVariantList SyncQueue::stuck() const
{
    QVariantList out;
    for (const QJsonObject &change : m_changes)
        if (change.value("failures").toInt() >= StuckAfter)
            out << change.toVariantMap();
    return out;
}

void SyncQueue::add(QJsonObject change)
{
    if (m_file.isEmpty())
        return;
    const QString op = change.value("op").toString();
    if (op == QLatin1String("stars") || op == QLatin1String("note")) {
        const int recipeId = change.value("recipeId").toInt();
        m_changes.removeIf([this, &op, recipeId](const QJsonObject &waiting) {
            return waiting.value("op").toString() == op && waiting.value("recipeId").toInt() == recipeId
                   && !m_sending.contains(waiting.value("id").toString());
        });
    }
    change.insert("id", QUuid::createUuid().toString(QUuid::WithoutBraces));
    change.insert("at", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs));
    change.insert("failures", 0);
    change.insert("message", QString());
    m_changes << change;
    save();
    emit changed();
    flush();
}

bool SyncQueue::dropMark(const QString &clientId)
{
    for (int i = 0; i < m_changes.size(); ++i) {
        const QJsonObject &change = m_changes.at(i);
        if (change.value("op").toString() == QLatin1String("devoured")
            && change.value("clientId").toString() == clientId && !m_sending.contains(change.value("id").toString())) {
            m_changes.removeAt(i);
            save();
            emit changed();
            return true;
        }
    }
    return false;
}

QVariantList SyncQueue::pendingMarks(int recipeId) const
{
    QVariantList out;
    for (const QJsonObject &change : m_changes)
        if (change.value("op").toString() == QLatin1String("devoured") && change.value("recipeId").toInt() == recipeId)
            out << QVariantMap{{"clientId", change.value("clientId").toString()}, {"on", change.value("on").toString()}};
    return out;
}

void SyncQueue::flush()
{
    m_refusedNow.clear();
    send();
}

void SyncQueue::retry(const QString &id)
{
    const int at = indexOf(id);
    if (at < 0)
        return;
    m_changes[at].insert("failures", 0);
    m_changes[at].insert("message", QString());
    save();
    emit changed();
    flush();
}

void SyncQueue::discard(const QString &id)
{
    const int at = indexOf(id);
    if (at < 0 || m_sending.contains(id))
        return;
    m_changes.removeAt(at);
    save();
    emit changed();
}

void SyncQueue::countFailure(int index, const QString &message)
{
    QJsonObject change = m_changes.at(index);
    change.insert("failures", change.value("failures").toInt() + 1);
    change.insert("message", message);
    m_changes[index] = change;
    m_refusedNow.insert(change.value("id").toString());
}

void SyncQueue::send()
{
    if (!m_sending.isEmpty() || m_file.isEmpty() || offline())
        return;
    QJsonArray ops;
    QStringList ids;
    for (const QJsonObject &change : m_changes) {
        const QString id = change.value("id").toString();
        if (change.value("failures").toInt() >= StuckAfter || m_refusedNow.contains(id))
            continue;
        ops.append(change);
        ids << id;
        if (ops.size() == BatchLimit)
            break;
    }
    if (ops.isEmpty())
        return;
    m_retry.stop();
    m_sending = QSet<QString>(ids.cbegin(), ids.cend());
    emit changed();
    const int epoch = m_epoch;
    m_api.post(QStringLiteral("/sync/batch"), QJsonObject{{"ops", ops}}, [this, epoch, ids](const Api::Result &result) {
        // Another account's queue now. Whatever the server took stays in the last account's file and is answered
        // "already" when that account sends it again.
        if (epoch != m_epoch)
            return;
        m_sending.clear();
        const QJsonArray answers = result.object.value("data").toObject().value("results").toArray();
        if (result.ok && answers.size() == ids.size()) {
            for (int i = 0; i < ids.size(); ++i) {
                const int at = indexOf(ids.at(i));
                if (at < 0)
                    continue;
                const QJsonObject answer = answers.at(i).toObject();
                if (answer.value("result").toString() == QLatin1String("refused")) {
                    countFailure(at, answer.value("message").toString());
                    continue;
                }
                const QJsonObject change = m_changes.takeAt(at);
                emit taken(change, answer);
            }
            save();
            emit changed();
            // A full batch leaves more behind; what was just refused waits for the next flush.
            if (ids.size() == BatchLimit)
                send();
            return;
        }
        if (result.httpStatus == 400) {
            // The batch itself was refused as malformed: each change in it counts a failure, so it can't block the
            // queue for ever.
            for (const QString &id : ids) {
                const int at = indexOf(id);
                if (at >= 0)
                    countFailure(at, reasonOf(result));
            }
            save();
            emit changed();
            return;
        }
        // No answer, a 5xx, a 401: nothing counts against the changes. Tried again in a while while the server
        // answers; otherwise on reconnect.
        emit changed();
        if (!offline())
            m_retry.start();
    }, BatchTimeoutMs);
}
