#include "services/Saved.h"

#include <QJsonArray>
#include <QJsonValue>
#include <QUrlQuery>


namespace {

QVariantList withoutId(const QVariantList &ids, int id)
{
    QVariantList kept;
    for (const QVariant &value : ids)
        if (value.toInt() != id)
            kept << value;
    return kept;
}

} // namespace


Saved::Saved(Api &api, QObject *parent) : QObject(parent), m_api(api), m_listRecipes(api, QString()) {}

QString Saved::cleanTitle(const QString &title)
{
    const QString trimmed = title.trimmed();
    const qsizetype length = trimmed.toUcs4().size();
    return length >= 1 && length <= TitleLimit ? trimmed : QString();
}

int Saved::indexOfList(int listId) const
{
    for (int i = 0; i < m_lists.size(); ++i)
        if (m_lists.at(i).toMap().value("id").toInt() == listId)
            return i;
    return -1;
}

QString Saved::listTitle(int listId) const
{
    const int at = indexOfList(listId);
    return at < 0 ? QString() : m_lists.at(at).toMap().value("title").toString();
}

void Saved::setCount(int listId, int count)
{
    const int at = indexOfList(listId);
    if (at < 0)
        return;
    QVariantMap list = m_lists.at(at).toMap();
    list.insert("count", count);
    m_lists[at] = list;
    emit listsChanged();
}

void Saved::noteFlag(int recipeId, const QString &key, const QVariant &value)
{
    m_flags[recipeId].insert(key, value);
    ++m_flagsRevision;
    emit flagsChanged();
}

void Saved::beginEdit()
{
    if (m_pending++ == 0)
        emit busyChanged();
}

void Saved::endEdit()
{
    if (m_pending > 0 && --m_pending == 0)
        emit busyChanged();
}

QVariantMap Saved::flagsOf(const QVariantMap &tile) const
{
    QVariantMap flags{{"craving", tile.value("craving").toBool()},
                      {"devouredCount", tile.value("devouredCount").toInt()},
                      {"stars", tile.value("stars").toInt()}};
    const auto changed = m_flags.constFind(tile.value("id").toInt());
    if (changed != m_flags.constEnd())
        for (auto it = changed->cbegin(); it != changed->cend(); ++it)
            flags.insert(it.key(), it.value());
    return flags;
}

void Saved::load()
{
    const int generation = m_generation;
    m_api.get(QStringLiteral("/lists"), QUrlQuery(), [this, generation](const Api::Result &result) {
        if (generation != m_generation)
            return;
        if (result.ok) {
            m_lists = result.object.value("data").toArray().toVariantList();
            m_cravingsId = 0;
            for (const QVariant &list : m_lists)
                if (list.toMap().value("kind").toString() == QLatin1String("cravings"))
                    m_cravingsId = list.toMap().value("id").toInt();
            m_listsLoaded = true;
            m_listsError.clear();
        } else {
            m_listsError = reasonOf(result);
        }
        emit listsChanged();
    });
}

void Saved::createList(const QString &title, int addRecipeId)
{
    const QString clean = cleanTitle(title);
    if (clean.isEmpty()) {
        emit failed(QStringLiteral("list"), QStringLiteral("A list title is 1 to 60 characters"));
        return;
    }
    if (m_listsLoaded && m_lists.size() >= ListLimit) {
        emit failed(QStringLiteral("list"), QStringLiteral("You can have at most 50 lists"));
        return;
    }
    const int generation = m_generation;
    beginEdit();
    m_api.post(QStringLiteral("/lists/create"), QJsonObject{{"title", clean}},
               [this, generation, addRecipeId](const Api::Result &result) {
        if (generation != m_generation)
            return;
        endEdit();
        if (!result.ok) {
            emit failed(QStringLiteral("list"), reasonOf(result));
            return;
        }
        const QVariantMap made = result.object.value("data").toObject().toVariantMap();
        m_lists.append(made);
        emit listsChanged();
        const int listId = made.value("id").toInt();
        emit listCreated(listId);
        emit done(QStringLiteral("list"));
        if (addRecipeId > 0)
            setInList(listId, addRecipeId, true);
    });
}

void Saved::renameList(int listId, const QString &title)
{
    const QString clean = cleanTitle(title);
    if (clean.isEmpty()) {
        emit failed(QStringLiteral("list"), QStringLiteral("A list title is 1 to 60 characters"));
        return;
    }
    const int generation = m_generation;
    beginEdit();
    m_api.post(QStringLiteral("/lists/rename"), QJsonObject{{"id", listId}, {"title", clean}},
               [this, generation, listId](const Api::Result &result) {
        if (generation != m_generation)
            return;
        endEdit();
        if (!result.ok) {
            emit failed(QStringLiteral("list"), reasonOf(result));
            return;
        }
        const int at = indexOfList(listId);
        if (at >= 0)
            m_lists[at] = result.object.value("data").toObject().toVariantMap();
        emit listsChanged();
        emit done(QStringLiteral("list"));
    });
}

void Saved::deleteList(int listId)
{
    const int generation = m_generation;
    beginEdit();
    m_api.post(QStringLiteral("/lists/delete"), QJsonObject{{"id", listId}},
               [this, generation, listId](const Api::Result &result) {
        if (generation != m_generation)
            return;
        endEdit();
        if (!result.ok) {
            emit failed(QStringLiteral("list"), reasonOf(result));
            return;
        }
        const int at = indexOfList(listId);
        if (at >= 0)
            m_lists.removeAt(at);
        if (m_openListId == listId) {
            m_openListId = 0;
            m_listRecipes.setPath(QString());
            emit openListChanged();
        }
        if (m_mineId > 0 && m_mine.contains("lists")) {
            m_mine.insert("lists", withoutId(m_mine.value("lists").toList(), listId));
            emit mineChanged();
        }
        emit listsChanged();
        emit done(QStringLiteral("list"));
    });
}

void Saved::moveList(int listId, int steps)
{
    const int from = indexOfList(listId);
    // Cravings is never moved, and nothing goes in front of it.
    if (from < 0 || m_lists.at(from).toMap().value("kind").toString() != QLatin1String("custom"))
        return;
    const int to = qBound(1, from + steps, int(m_lists.size()) - 1);
    if (to == from)
        return;
    m_lists.move(from, to);
    emit listsChanged();
    QJsonObject body{{"id", listId}};
    body.insert("after", to == 1 ? QJsonValue() : QJsonValue(m_lists.at(to - 1).toMap().value("id").toInt()));
    const int generation = m_generation;
    m_api.post(QStringLiteral("/lists/reorder"), body, [this, generation](const Api::Result &result) {
        if (generation != m_generation || result.ok)
            return;
        // The server holds another order: show the lists as it has them.
        emit failed(QStringLiteral("lists"), reasonOf(result));
        load();
    });
}

void Saved::openList(int listId)
{
    if (listId <= 0)
        return;
    const bool other = listId != m_openListId;
    m_openListId = listId;
    m_listRecipes.setPath(QStringLiteral("/lists/%1/recipes").arg(listId));
    if (m_openStale && !other && m_listRecipes.answered())
        m_listRecipes.reload();
    else
        m_listRecipes.run(QUrlQuery());
    m_openStale = false;
    if (other)
        emit openListChanged();
}

void Saved::setCraving(int recipeId, bool craving)
{
    if (m_cravingsId <= 0) {
        // The lists have not loaded (or failed to): ask for them, and say why nothing changed.
        emit failed(QStringLiteral("item"), m_listsError.isEmpty() ? QStringLiteral("Your lists are still loading")
                                                                    : m_listsError);
        load();
        return;
    }
    setInList(m_cravingsId, recipeId, craving);
}

void Saved::setInList(int listId, int recipeId, bool in)
{
    if (listId <= 0 || recipeId <= 0)
        return;
    const int generation = m_generation;
    const QJsonObject body{{"listId", listId}, {"recipeId", recipeId}};
    m_api.post(in ? QStringLiteral("/lists/items/add") : QStringLiteral("/lists/items/remove"), body,
               [this, generation, listId, recipeId, in](const Api::Result &result) {
        if (generation != m_generation)
            return;
        if (!result.ok) {
            emit failed(QStringLiteral("item"), reasonOf(result));
            return;
        }
        setCount(listId, result.object.value("data").toObject().value("count").toInt());
        const bool cravings = listId == m_cravingsId;
        if (cravings)
            noteFlag(recipeId, QStringLiteral("craving"), in);
        if (listId == m_openListId) {
            if (in)
                m_openStale = true;
            else
                m_listRecipes.dropRecipe(recipeId);
        }
        if (recipeId == m_mineId) {
            if (cravings) {
                m_mine.insert("craving", in);
            } else {
                QVariantList ids = withoutId(m_mine.value("lists").toList(), listId);
                if (in)
                    ids << listId;
                m_mine.insert("lists", ids);
            }
            emit mineChanged();
        }
        if (cravings)
            emit keptChanged();
    });
}

void Saved::moveItem(int from, int to)
{
    const int count = m_listRecipes.count();
    if (m_openListId <= 0 || from == to || from < 0 || to < 0 || from >= count || to >= count)
        return;
    const int recipeId = m_listRecipes.rowAt(from).value("id").toInt();
    m_listRecipes.moveRecipe(from, to);
    QJsonObject body{{"listId", m_openListId}, {"recipeId", recipeId}};
    body.insert("after", to == 0 ? QJsonValue() : QJsonValue(m_listRecipes.rowAt(to - 1).value("id").toInt()));
    m_moves.append(body);
    sendNextMove();
}

void Saved::sendNextMove()
{
    // One at a time: two requests at once may reach the server in either order, and each move names what the
    // recipe follows as the grid stood after the move before it.
    if (m_moving || m_moves.isEmpty())
        return;
    m_moving = true;
    const QJsonObject body = m_moves.takeFirst();
    const int generation = m_generation;
    m_api.post(QStringLiteral("/lists/items/reorder"), body, [this, generation](const Api::Result &result) {
        if (generation != m_generation)
            return;
        m_moving = false;
        if (!result.ok) {
            // The list changed on the server (a recipe left it elsewhere): the moves still waiting were made on
            // an order it no longer holds, so they go, and the list is shown as the server has it.
            m_moves.clear();
            emit failed(QStringLiteral("move"), reasonOf(result));
            m_listRecipes.reload();
            return;
        }
        sendNextMove();
    });
}

void Saved::showMine(int recipeId, const QVariantMap &mine)
{
    m_mineId = recipeId;
    m_mine = recipeId > 0 ? mine : QVariantMap();
    // The detail is the newest word on this recipe, so its tiles agree with it from now on.
    if (recipeId > 0 && !mine.isEmpty()) {
        QVariantMap &flags = m_flags[recipeId];
        flags.insert("craving", mine.value("craving").toBool());
        flags.insert("devouredCount", int(mine.value("devoured").toList().size()));
        flags.insert("stars", mine.value("stars").toInt());
        ++m_flagsRevision;
        emit flagsChanged();
    }
    emit mineChanged();
}

void Saved::clear()
{
    ++m_generation;
    m_lists.clear();
    m_cravingsId = 0;
    m_listsLoaded = false;
    m_listsError.clear();
    m_openListId = 0;
    m_openStale = false;
    m_listRecipes.setPath(QString());
    m_listRecipes.clear();
    m_flags.clear();
    ++m_flagsRevision;
    m_mineId = 0;
    m_mine.clear();
    m_moves.clear();
    m_moving = false;
    const bool wasBusy = m_pending > 0;
    m_pending = 0;
    emit listsChanged();
    emit openListChanged();
    emit flagsChanged();
    emit mineChanged();
    if (wasBusy)
        emit busyChanged();
}
