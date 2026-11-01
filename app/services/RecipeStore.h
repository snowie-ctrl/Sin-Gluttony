#pragma once
#include <QHash>
#include <QList>
#include <QObject>
#include <QPair>
#include <QSet>
#include <QString>
#include <QVariantList>
#include <QVariantMap>

#include <functional>

#include "api/Api.h"

class AccountStore;
class QNetworkAccessManager;


// The saved recipes kept on this device (spec §6), so they open with no server: every recipe on the person's lists
// (Cravings included) and every one opened in cook mode in the last 30 days, each as its detail
// (recipes/<id>.json) and its large picture (<id>.jpg) in the account's folder, beside the lists as the last
// manifest had them (manifest.json).
//
// At sign-in (the token's arrival) and whenever the server answers again, GET /saved/manifest says what is kept and
// when part 1 last changed each recipe: a copy that is missing or older is fetched again, four at a time, and one
// that is no longer kept is deleted. A manifest that fails deletes nothing, so an outage never empties the shelf.
// With no server, the Saved page, Home's rows and search read the copies here. A copy's picture is read from disk
// whenever there is one, online or not, and stands in for the thumbnail too.
class RecipeStore : public QObject
{
    Q_OBJECT

    // Bumped whenever a copy, a picture or the lists change, so bindings that call pictureUrl(), tilesOf() or
    // search() are evaluated again.
    Q_PROPERTY(int revision READ revision NOTIFY changed)
    // [{id, title, kind, count}] as the last manifest had them, Cravings first; count is the list's recipes.
    Q_PROPERTY(QVariantList lists READ lists NOTIFY changed)
    // Home's rows with no server: the copies on Cravings in its order, and the copies devoured, newest mark first.
    Q_PROPERTY(QVariantList cravings READ cravings NOTIFY changed)
    Q_PROPERTY(QVariantList again READ again NOTIFY changed)
    Q_PROPERTY(bool refreshing READ refreshing NOTIFY refreshingChanged)

public:
    // A cook-mode copy that is on no list is kept this long after it was last cooked.
    static constexpr qint64 CookKeepMs = 30LL * 24 * 60 * 60 * 1000;
    static constexpr int ExtraLimit = 200;
    // Home's offline rows show as many tiles as its online ones (the server's HOME_ROW).
    static constexpr int RowLimit = 12;
    static constexpr int SearchLimit = 20;
    // Details (and their pictures) fetched at once during a refresh.
    static constexpr int Parallel = 4;

    explicit RecipeStore(Api &api, QObject *parent = nullptr);

    // The account whose copies these are; they follow its folder through sign-in and sign-out.
    void setStore(AccountStore *store);
    // Milliseconds since the epoch; tests move it forward instead of waiting.
    void setClock(std::function<qint64()> clock) { m_clock = std::move(clock); }

    int revision() const { return m_revision; }
    QVariantList lists() const;
    QVariantList cravings() const;
    QVariantList again() const;
    bool refreshing() const { return m_refreshing; }

    bool has(int recipeId) const { return m_index.contains(recipeId); }
    // The copy's detail (with its `mine`), or an empty map.
    QVariantMap recipe(int recipeId) const;
    // A picture as an Image source: the copy's file when it has one, the server's address otherwise.
    Q_INVOKABLE QString pictureUrl(int recipeId, bool large) const;
    // A list's copies as tiles, in the list's order; a recipe whose copy is not here yet is left out.
    Q_INVOKABLE QVariantList tilesOf(int listId) const;
    // The copies whose title holds `text` (case aside), by title: search with no server.
    Q_INVOKABLE QVariantList search(const QString &text) const;

    // Cook mode opened this recipe: it is kept, marked as cooked now, and its picture fetched if it can be.
    void keepForCooking(const QVariantMap &recipe);
    // A fresher detail of a recipe that has a copy (the recipe page loaded it): the copy takes it. Nothing otherwise.
    void update(const QVariantMap &recipe);
    // What the person keeps on a recipe changed (offline, or since its copy was made): the copy says so too.
    void patchMine(int recipeId, const QVariantMap &mine);
    // Whether this device still has a change of its own waiting for a recipe (Wiring passes SyncQueue::waits). Such
    // a copy keeps its `mine` when the manifest says otherwise: the manifest may have been read before the change
    // reached the server.
    void setWaiting(std::function<bool(int)> waiting) { m_waiting = std::move(waiting); }
    // Asks for the manifest and brings the copies in line with it. A second ask while one is on its way runs once
    // that one has finished.
    Q_INVOKABLE void refresh();

signals:
    void changed();
    void refreshingChanged();

private:
    // What is known of a copy without reading its file again.
    struct Entry
    {
        QVariantMap tile;
        QString updatedAt;
        qint64 cookedAt = 0;
        bool picture = false;
        // The newest Devoured mark's day, "" when none: Again?'s order.
        QString lastMadeOn;
        // What the person keeps on it, as the copy holds it: compared with the manifest's.
        QVariantMap mine;
    };

    void load();
    Entry entryOf(int recipeId, const QVariantMap &recipe, const QString &updatedAt, qint64 cookedAt) const;
    void write(int recipeId, const QVariantMap &recipe, const QString &updatedAt, qint64 cookedAt);
    void remove(int recipeId);
    void fetchNext();
    void fetchDetail(int recipeId, const QString &updatedAt);
    // `counted`: the fetch holds one of the refresh's slots (a detail's picture does; a cooked recipe's, which can
    // land while the manifest is still on its way, must not look like the end of the refresh).
    void fetchPicture(int recipeId, bool counted);
    void finishRefresh();
    void bump();
    bool offline() const;
    // A change of this device's own waits for the recipe, now or when this refresh asked: its copy's `mine` stands.
    bool keepsOwnMine(int recipeId) const;
    QString pictureFile(int recipeId) const;
    static QVariantMap tileOf(const QVariantMap &recipe);

    Api &m_api;
    AccountStore *m_store = nullptr;
    std::function<qint64()> m_clock;
    std::function<bool(int)> m_waiting;
    // The recipes that had a change waiting when the running refresh asked for the manifest.
    QSet<int> m_waitedAtAsk;
    // Pictures go through a manager that adds the session token, as every Image's does (AuthNetworkFactory).
    QNetworkAccessManager *m_network;
    QHash<int, Entry> m_index;
    // The manifest's lists, each with its recipeIds.
    QVariantList m_lists;
    int m_revision = 0;
    bool m_refreshing = false;
    bool m_refreshAgain = false;
    // (recipe, the manifest's updatedAt) still to fetch in this refresh.
    QList<QPair<int, QString>> m_toFetch;
    int m_inFlight = 0;
    // Bumped when the account changes: an answer for the last one is dropped.
    int m_generation = 0;
};
