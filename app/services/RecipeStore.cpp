#include "services/RecipeStore.h"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkReply>
#include <QSaveFile>
#include <QUrl>
#include <QUrlQuery>

#include <algorithm>
#include <utility>

#include "api/AuthNetworkFactory.h"
#include "services/AccountStore.h"

// Compared as JSON text: a copy read back from disk and one Saved patched hold the same values in different types
// (a whole number or a double, no value or a null).
static bool sameMine(const QVariantMap &a, const QVariantMap &b)
{
    return QJsonDocument(QJsonObject::fromVariantMap(a)).toJson(QJsonDocument::Compact)
        == QJsonDocument(QJsonObject::fromVariantMap(b)).toJson(QJsonDocument::Compact);
}

RecipeStore::RecipeStore(Api &api, QObject *parent)
    : QObject(parent)
    , m_api(api)
    , m_clock([]() { return QDateTime::currentMSecsSinceEpoch(); })
    , m_network(new AuthNetworkAccessManager(this))
{
    // Spec §6: at sign-in (the token arrives) and on reconnect, the copies are brought up to date.
    connect(&m_api, &Api::sessionTokenChanged, this, [this]() {
        if (!offline())
            refresh();
    });
    connect(&m_api, &Api::onlineChanged, this, [this]() {
        if (!offline())
            refresh();
    });
}

bool RecipeStore::offline() const
{
    return !m_api.online() || m_api.sessionToken().isEmpty();
}

void RecipeStore::setStore(AccountStore *store)
{
    m_store = store;
    connect(store, &AccountStore::changed, this, &RecipeStore::load);
    load();
}

QString RecipeStore::pictureFile(int recipeId) const
{
    const QString dir = m_store ? m_store->recipesDir() : QString();
    return dir.isEmpty() ? QString() : dir + QStringLiteral("/%1.jpg").arg(recipeId);
}

QVariantMap RecipeStore::tileOf(const QVariantMap &recipe)
{
    QVariantMap tile;
    for (const char *key : {"id", "kind", "title", "course", "cuisine", "totalMinutes", "timeFrom", "difficulty",
                            "hasImage", "source", "removed"})
        tile.insert(QLatin1String(key), recipe.value(QLatin1String(key)));
    // The flags every tile carries, from what the copy says the person keeps.
    const QVariantMap mine = recipe.value("mine").toMap();
    tile.insert("craving", mine.value("craving").toBool());
    tile.insert("devouredCount", int(mine.value("devoured").toList().size()));
    tile.insert("stars", mine.value("stars").toInt());
    return tile;
}

RecipeStore::Entry RecipeStore::entryOf(int recipeId, const QVariantMap &recipe, const QString &updatedAt,
                                        qint64 cookedAt) const
{
    Entry entry;
    entry.tile = tileOf(recipe);
    entry.updatedAt = updatedAt;
    entry.cookedAt = cookedAt;
    entry.mine = recipe.value("mine").toMap();
    entry.picture = QFile::exists(pictureFile(recipeId));
    for (const QVariant &mark : recipe.value("mine").toMap().value("devoured").toList())
        entry.lastMadeOn = qMax(entry.lastMadeOn, mark.toMap().value("on").toString());
    return entry;
}

void RecipeStore::load()
{
    // Another account, or none: anything on its way was for the last one.
    ++m_generation;
    m_index.clear();
    m_lists.clear();
    m_toFetch.clear();
    m_inFlight = 0;
    m_refreshAgain = false;
    const bool wasRefreshing = std::exchange(m_refreshing, false);
    const QString dir = m_store ? m_store->recipesDir() : QString();
    if (!dir.isEmpty()) {
        for (const QString &name : QDir(dir).entryList({QStringLiteral("*.json")}, QDir::Files)) {
            const int id = name.chopped(5).toInt();
            const QJsonObject copy = AccountStore::readJson(dir + QLatin1Char('/') + name);
            const QVariantMap recipe = copy.value("recipe").toObject().toVariantMap();
            // A file that is not a copy of the recipe it is named for is not trusted.
            if (id <= 0 || recipe.value("id").toInt() != id)
                continue;
            m_index.insert(id, entryOf(id, recipe, copy.value("updatedAt").toString(),
                                       qint64(copy.value("cookedAt").toDouble())));
        }
        m_lists = AccountStore::readJson(m_store->file(QStringLiteral("manifest.json"))).value("lists").toArray()
                      .toVariantList();
    }
    if (wasRefreshing)
        emit refreshingChanged();
    bump();
}

void RecipeStore::bump()
{
    ++m_revision;
    emit changed();
}

QVariantMap RecipeStore::recipe(int recipeId) const
{
    if (!has(recipeId) || !m_store)
        return {};
    return AccountStore::readJson(m_store->recipeFile(recipeId)).value("recipe").toObject().toVariantMap();
}

QString RecipeStore::pictureUrl(int recipeId, bool large) const
{
    const auto found = m_index.constFind(recipeId);
    if (found != m_index.cend() && found->picture)
        return QUrl::fromLocalFile(pictureFile(recipeId)).toString();
    return m_api.pictureUrl(large ? QStringLiteral("images") : QStringLiteral("thumbs"), recipeId);
}

QVariantList RecipeStore::lists() const
{
    QVariantList out;
    for (const QVariant &value : m_lists) {
        const QVariantMap list = value.toMap();
        out << QVariantMap{{"id", list.value("id")}, {"title", list.value("title")}, {"kind", list.value("kind")},
                           {"count", int(list.value("recipeIds").toList().size())}};
    }
    return out;
}

QVariantList RecipeStore::tilesOf(int listId) const
{
    QVariantList out;
    for (const QVariant &value : m_lists) {
        const QVariantMap list = value.toMap();
        if (list.value("id").toInt() != listId)
            continue;
        for (const QVariant &id : list.value("recipeIds").toList()) {
            const auto found = m_index.constFind(id.toInt());
            if (found != m_index.cend())
                out << found->tile;
        }
    }
    return out;
}

QVariantList RecipeStore::cravings() const
{
    for (const QVariant &value : m_lists)
        if (value.toMap().value("kind").toString() == QLatin1String("cravings"))
            return tilesOf(value.toMap().value("id").toInt()).mid(0, RowLimit);
    return {};
}

QVariantList RecipeStore::again() const
{
    QList<QPair<QString, int>> made;
    for (auto it = m_index.cbegin(); it != m_index.cend(); ++it)
        if (!it->lastMadeOn.isEmpty())
            made << qMakePair(it->lastMadeOn, it.key());
    // Newest day first, then the higher id, so the order holds from one look to the next.
    std::sort(made.begin(), made.end(), [](const auto &a, const auto &b) { return a > b; });
    QVariantList out;
    for (int i = 0; i < made.size() && i < RowLimit; ++i)
        out << m_index.value(made.at(i).second).tile;
    return out;
}

QVariantList RecipeStore::search(const QString &text) const
{
    const QString wanted = text.trimmed();
    if (wanted.isEmpty())
        return {};
    QList<QVariantMap> found;
    for (const Entry &entry : m_index)
        if (entry.tile.value("title").toString().contains(wanted, Qt::CaseInsensitive))
            found << entry.tile;
    std::sort(found.begin(), found.end(), [](const QVariantMap &a, const QVariantMap &b) {
        return QString::localeAwareCompare(a.value("title").toString(), b.value("title").toString()) < 0;
    });
    QVariantList out;
    for (int i = 0; i < found.size() && i < SearchLimit; ++i)
        out << found.at(i);
    return out;
}

void RecipeStore::write(int recipeId, const QVariantMap &recipe, const QString &updatedAt, qint64 cookedAt)
{
    const QString file = m_store ? m_store->recipeFile(recipeId) : QString();
    if (file.isEmpty())
        return;
    AccountStore::writeJson(file, QJsonObject{{"recipe", QJsonObject::fromVariantMap(recipe)},
                                              {"updatedAt", updatedAt}, {"cookedAt", double(cookedAt)}});
    m_index.insert(recipeId, entryOf(recipeId, recipe, updatedAt, cookedAt));
    bump();
}

void RecipeStore::remove(int recipeId)
{
    if (!m_store || !m_index.remove(recipeId))
        return;
    QFile::remove(m_store->recipeFile(recipeId));
    QFile::remove(pictureFile(recipeId));
    bump();
}

void RecipeStore::keepForCooking(const QVariantMap &recipe)
{
    const int id = recipe.value("id").toInt();
    if (id <= 0 || !m_store || m_store->uid() <= 0)
        return;
    // A saved recipe keeps its manifest stamp, so the next refresh does not fetch it again.
    const Entry known = m_index.value(id);
    write(id, recipe, known.updatedAt, m_clock());
    if (recipe.value("hasImage").toBool() && !m_index.value(id).picture && !offline()) {
        fetchPicture(id, false);
    }
}

void RecipeStore::update(const QVariantMap &recipe)
{
    const int id = recipe.value("id").toInt();
    if (!has(id))
        return;
    const Entry known = m_index.value(id);
    write(id, recipe, known.updatedAt, known.cookedAt);
}

void RecipeStore::patchMine(int recipeId, const QVariantMap &mine)
{
    if (!has(recipeId))
        return;
    QVariantMap copy = recipe(recipeId);
    if (copy.isEmpty())
        return;
    copy.insert("mine", mine);
    const Entry known = m_index.value(recipeId);
    write(recipeId, copy, known.updatedAt, known.cookedAt);
}

void RecipeStore::refresh()
{
    if (!m_store || m_store->uid() <= 0 || offline())
        return;
    if (m_refreshing) {
        m_refreshAgain = true;
        return;
    }
    m_refreshing = true;
    emit refreshingChanged();
    // The cook-mode copies of the last 30 days, most recently cooked first, are named so the server says whether
    // the person may still see them; older ones are not named, and so go below.
    QList<QPair<qint64, int>> cooked;
    const qint64 now = m_clock();
    for (auto it = m_index.cbegin(); it != m_index.cend(); ++it)
        if (it->cookedAt > 0 && now - it->cookedAt < CookKeepMs)
            cooked << qMakePair(it->cookedAt, it.key());
    std::sort(cooked.begin(), cooked.end(), [](const auto &a, const auto &b) { return a > b; });
    QStringList extra;
    for (int i = 0; i < cooked.size() && i < ExtraLimit; ++i)
        extra << QString::number(cooked.at(i).second);
    QUrlQuery query;
    if (!extra.isEmpty())
        query.addQueryItem(QStringLiteral("extra"), extra.join(QLatin1Char(',')));

    const int generation = m_generation;
    const qint64 askedAt = now;
    m_api.get(QStringLiteral("/saved/manifest"), query, [this, generation, askedAt](const Api::Result &result) {
        if (generation != m_generation)
            return;
        if (!result.ok) {
            // An outage or a refusal says nothing about what to keep: everything stays.
            finishRefresh();
            return;
        }
        const QJsonObject data = result.object.value("data").toObject();
        // A 200 that is not a manifest (a proxy's page, a server half-deployed) names nothing to keep or to drop, and
        // reading it as an empty manifest would empty the offline shelf.
        if (!data.value("lists").isArray() || !data.value("recipes").isArray()) {
            finishRefresh();
            return;
        }
        m_lists = data.value("lists").toArray().toVariantList();
        AccountStore::writeJson(m_store->file(QStringLiteral("manifest.json")),
                                QJsonObject{{"lists", data.value("lists")}});
        QHash<int, QString> wanted;
        QHash<int, QVariantMap> mines;
        for (const QJsonValue &value : data.value("recipes").toArray()) {
            const QJsonObject entry = value.toObject();
            const int id = entry.value("id").toInt();
            wanted.insert(id, entry.value("updatedAt").toString());
            if (entry.value("mine").isObject())
                mines.insert(id, entry.value("mine").toObject().toVariantMap());
        }
        // A recipe cooked since the manifest was asked for is not named in it yet: it stays.
        for (const int id : m_index.keys())
            if (!wanted.contains(id) && m_index.value(id).cookedAt < askedAt)
                remove(id);
        m_toFetch.clear();
        QList<int> minesToPatch;
        for (auto it = wanted.cbegin(); it != wanted.cend(); ++it) {
            const auto known = m_index.constFind(it.key());
            const bool stale = known == m_index.cend() || known->updatedAt != it.value();
            const bool pictureMissing = known != m_index.cend() && known->tile.value("hasImage").toBool() && !known->picture;
            if (stale || pictureMissing)
                m_toFetch << qMakePair(it.key(), it.value());
            // Stars, a note, a mark or a list changed on another device: the copy takes the server's `mine` without
            // fetching the recipe again (a stale one is fetched whole, `mine` and all). Not while a change of this
            // device's own still waits for the recipe: the queue's answer asks for the manifest again.
            if (!stale && mines.contains(it.key()) && !(m_waiting && m_waiting(it.key()))
                && !sameMine(known->mine, mines.value(it.key())))
                minesToPatch << it.key();
        }
        // Patched after the walk: writing a copy changes the index the walk reads.
        for (const int id : minesToPatch)
            patchMine(id, mines.value(id));
        // Lowest id first, so a refresh fetches in a repeatable order.
        std::sort(m_toFetch.begin(), m_toFetch.end());
        bump();
        fetchNext();
    });
}

void RecipeStore::fetchNext()
{
    while (m_inFlight < Parallel && !m_toFetch.isEmpty()) {
        const auto next = m_toFetch.takeFirst();
        fetchDetail(next.first, next.second);
    }
    if (m_refreshing && m_inFlight == 0 && m_toFetch.isEmpty())
        finishRefresh();
}

void RecipeStore::fetchDetail(int recipeId, const QString &updatedAt)
{
    ++m_inFlight;
    const int generation = m_generation;
    m_api.get(QStringLiteral("/recipes/%1").arg(recipeId), QUrlQuery(),
              [this, generation, recipeId, updatedAt](const Api::Result &result) {
        if (generation != m_generation)
            return;
        if (result.ok) {
            const QVariantMap recipe = result.object.value("data").toObject().toVariantMap();
            write(recipeId, recipe, updatedAt, m_index.value(recipeId).cookedAt);
            if (recipe.value("hasImage").toBool()) {
                // The slot stays counted until the picture has landed too.
                fetchPicture(recipeId, true);
                return;
            }
        } else if (result.httpStatus == 404 && !result.object.isEmpty()) {
            // The server says it is gone, or no longer the person's to see: the copy goes with it. A 404 that is not
            // the server's own (a proxy's page, which has no JSON) says nothing about this recipe.
            remove(recipeId);
        } else if (result.httpStatus == 0) {
            // The server went away mid-refresh: the rest waits for the next one.
            m_toFetch.clear();
        }
        --m_inFlight;
        fetchNext();
    });
}

void RecipeStore::fetchPicture(int recipeId, bool counted)
{
    const int generation = m_generation;
    const QString file = pictureFile(recipeId);
    QNetworkRequest request(QUrl(m_api.pictureUrl(QStringLiteral("images"), recipeId)));
    request.setTransferTimeout(20000);
    QNetworkReply *reply = m_network->get(request);
    connect(reply, &QNetworkReply::finished, this, [this, reply, generation, recipeId, file, counted]() {
        reply->deleteLater();
        if (generation != m_generation)
            return;
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (reply->error() == QNetworkReply::NoError && status == 200 && m_index.contains(recipeId)) {
            QSaveFile out(file);
            if (out.open(QIODevice::WriteOnly)) {
                out.write(reply->readAll());
                if (out.commit()) {
                    m_index[recipeId].picture = true;
                    bump();
                }
            }
        }
        if (counted) {
            --m_inFlight;
            fetchNext();
        }
    });
}

void RecipeStore::finishRefresh()
{
    m_refreshing = false;
    emit refreshingChanged();
    if (std::exchange(m_refreshAgain, false))
        refresh();
}
