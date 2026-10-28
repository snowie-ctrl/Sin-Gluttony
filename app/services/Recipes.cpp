#include "services/Recipes.h"

#include <QJsonObject>
#include <QUrlQuery>


Recipes::Recipes(Api &api, QObject *parent) : QObject(parent), m_api(api) {}

void Recipes::open(int recipeId)
{
    if (recipeId <= 0)
        return;
    if (recipeId == m_recipeId && (m_loading || (!m_recipe.isEmpty() && m_error.isEmpty())))
        return;
    m_recipeId = recipeId;
    m_recipe.clear();
    m_servings = 0;
    m_multiplier = 1.0;
    fetch();
}

void Recipes::reload()
{
    if (m_recipeId > 0)
        fetch();
}

void Recipes::fetch()
{
    const int generation = ++m_generation;
    m_loading = true;
    m_gone = false;
    m_error.clear();
    emit changed();
    m_api.get(QStringLiteral("/recipes/%1").arg(m_recipeId), QUrlQuery(), [this, generation](const Api::Result &result) {
        if (generation != m_generation)
            return;
        m_loading = false;
        if (result.ok) {
            m_recipe = result.object.value("data").toObject().toVariantMap();
            m_servings = qMax(0, m_recipe.value("servings").toInt());
            m_multiplier = 1.0;
        } else if (result.httpStatus == 404) {
            m_gone = true;
        } else {
            m_error = reasonOf(result);
        }
        emit changed();
        emit servingsChanged();
    });
}

void Recipes::setServings(int servings)
{
    // A recipe that states no servings is scaled by the multiplier instead.
    if (m_recipe.value("servings").toInt() <= 0)
        return;
    const int bounded = qBound(1, servings, 99);
    if (bounded == m_servings)
        return;
    m_servings = bounded;
    emit servingsChanged();
}

void Recipes::setMultiplier(double multiplier)
{
    const double bounded = qBound(0.25, multiplier, 10.0);
    if (qFuzzyCompare(bounded, m_multiplier))
        return;
    m_multiplier = bounded;
    emit servingsChanged();
}

void Recipes::clear()
{
    ++m_generation;
    m_recipeId = -1;
    m_recipe.clear();
    m_loading = false;
    m_gone = false;
    m_error.clear();
    m_servings = 0;
    m_multiplier = 1.0;
    emit changed();
    emit servingsChanged();
}
