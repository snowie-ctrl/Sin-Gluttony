#pragma once
#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QSet>
#include <QString>
#include <QTimer>
#include <QVariantList>

#include "api/Api.h"

class AccountStore;


// What the person did with no server (spec §6): Devoured marks, stars and notes, kept in the account's
// sync-queue.json and sent with /sync/batch when the server answers again (on reconnect, when the session's token
// arrives, and at once when something is added while it answers). The server applies them oldest first and answers
// each: a change it took (applied, or it already held that change or a newer one) leaves the queue and is announced
// (taken), so what is shown can follow what the server kept.
//
// A change the server refuses counts a failure and is tried again at the next send; after 5 it is stuck, and waits
// in Settings › Waiting to sync for Try again or Discard. No answer, a 5xx or a 401 counts nothing: the change
// simply waits, and is tried again in a while. A change sent again after its answer was lost is harmless: a mark
// carries its clientId, a star or note its moment, and the server answers "already".
class SyncQueue : public QObject
{
    Q_OBJECT

    // Every change waiting, stuck ones included.
    Q_PROPERTY(int count READ count NOTIFY changed)
    // The stuck changes: [{id, op, recipeId, title, on, stars, text, failures, message}], oldest first.
    Q_PROPERTY(QVariantList stuck READ stuck NOTIFY changed)
    Q_PROPERTY(bool sending READ sending NOTIFY changed)

public:
    static constexpr int BatchLimit = 500;
    static constexpr int StuckAfter = 5;
    // A batch is a big body and the server's work, so it gets longer than Api's 20 s.
    static constexpr int BatchTimeoutMs = 60000;

    explicit SyncQueue(Api &api, QObject *parent = nullptr);

    // The queue's file follows the open account's folder.
    void setStore(AccountStore *store);
    // How long a batch that met no answer or a 5xx waits before it is tried again (15 s); tests shorten it.
    void setRetryDelay(int ms) { m_retry.setInterval(ms); }

    int count() const { return int(m_changes.size()); }
    QVariantList stuck() const;
    bool sending() const { return !m_sending.isEmpty(); }
    QList<QJsonObject> changes() const { return m_changes; }

    // A change made with no server: {op, recipeId, title, and on + clientId, stars, or text}. It is given an id and
    // the moment (UTC). A star or note replaces the one waiting for the same recipe, unless that one is on its way:
    // only the newest matters, and the server keeps the newest anyway.
    void add(QJsonObject change);
    // A queued mark taken back before it was sent. False when it is not waiting (on its way, sent, or never queued).
    bool dropMark(const QString &clientId);
    // The marks waiting for one recipe, oldest first: [{clientId, on}].
    QVariantList pendingMarks(int recipeId) const;

    // Sends what waits (not what is stuck), at most 500 a batch, when the server answers and there is a session.
    Q_INVOKABLE void flush();
    // A stuck change is tried again from nothing.
    Q_INVOKABLE void retry(const QString &id);
    Q_INVOKABLE void discard(const QString &id);

signals:
    void changed();
    // The server took this change: `result` is its answer (with the stars, note, or mark it now holds).
    void taken(const QJsonObject &change, const QJsonObject &result);

private:
    void load();
    void save();
    void send();
    bool offline() const;
    int indexOf(const QString &id) const;
    void countFailure(int index, const QString &message);

    Api &m_api;
    AccountStore *m_store = nullptr;
    QString m_file;
    QList<QJsonObject> m_changes;
    // The ids of the changes on their way.
    QSet<QString> m_sending;
    // The ids refused since the last flush(): a full batch's follow-up does not send them again at once.
    QSet<QString> m_refusedNow;
    // Bumped when the account changes: an answer for the last one is dropped.
    int m_epoch = 0;
    QTimer m_retry;
};
