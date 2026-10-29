#include "services/RecipeQuery.h"

#include <QJsonArray>
#include <QJsonObject>


RecipeQuery::RecipeQuery(Api &api, const QString &path, QObject *parent) : QObject(parent), m_api(api), m_path(path) {}

void RecipeQuery::setPath(const QString &path)
{
    if (path == m_path)
        return;
    m_path = path;
    ++m_generation;
    m_model.clearRows();
    m_hasQuery = false;
    m_total = 0;
    m_page = 0;
    m_loading = false;
    m_answered = false;
    m_error.clear();
    emit changed();
}

void RecipeQuery::dropRecipe(int recipeId)
{
    if (!exhausted()) {
        reload();
        return;
    }
    if (m_model.removeRecipe(recipeId)) {
        m_total = qMax(0, m_total - 1);
        emit changed();
    }
}

void RecipeQuery::run(const QUrlQuery &query)
{
    if (m_hasQuery && query == m_query && (m_loading || (m_answered && m_error.isEmpty())))
        return;
    m_query = query;
    m_hasQuery = true;
    restart();
}

void RecipeQuery::reload()
{
    if (m_hasQuery)
        restart();
}

void RecipeQuery::restart()
{
    ++m_generation;
    m_model.clearRows();
    m_total = 0;
    m_page = 0;
    m_answered = false;
    m_error.clear();
    fetch(1);
}

void RecipeQuery::more()
{
    if (!m_hasQuery || m_loading || !m_answered || exhausted())
        return;
    fetch(m_page + 1);
}

void RecipeQuery::fetch(int page)
{
    QUrlQuery query = m_query;
    query.addQueryItem(QStringLiteral("page"), QString::number(page));
    query.addQueryItem(QStringLiteral("pageSize"), QString::number(PageSize));
    m_loading = true;
    emit changed();
    const int generation = m_generation;
    m_api.get(m_path, query, [this, generation, page](const Api::Result &result) {
        if (generation != m_generation)
            return;
        m_loading = false;
        m_answered = true;
        if (result.ok) {
            const QJsonObject data = result.object.value("data").toObject();
            m_total = data.value("total").toInt();
            m_model.appendRows(data.value("recipes").toArray().toVariantList());
            m_page = page;
            m_error.clear();
        } else {
            m_error = reasonOf(result);
        }
        emit changed();
    });
}

void RecipeQuery::clear()
{
    ++m_generation;
    m_model.clearRows();
    m_query = QUrlQuery();
    m_hasQuery = false;
    m_total = 0;
    m_page = 0;
    m_loading = false;
    m_answered = false;
    m_error.clear();
    emit changed();
}
