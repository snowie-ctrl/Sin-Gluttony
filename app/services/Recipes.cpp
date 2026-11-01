#include "services/Recipes.h"

#include <QJsonObject>
#include <QUrlQuery>

#include "services/RecipeStore.h"


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
    // With no server the copy kept on this device is the recipe (spec §6), without a request that can only fail.
    if (offline() && openCopy())
        return;
    fetch();
}

void Recipes::reload()
{
    if (m_recipeId <= 0)
        return;
    if (offline() && openCopy())
        return;
    fetch();
}

bool Recipes::offline() const
{
    return !m_api.online() || m_api.sessionToken().isEmpty();
}

bool Recipes::openCopy()
{
    const QVariantMap copy = m_store ? m_store->recipe(m_recipeId) : QVariantMap();
    if (copy.isEmpty())
        return false;
    // Whatever was on its way for this recipe is superseded by the copy.
    ++m_generation;
    m_recipe = copy;
    m_loading = false;
    m_gone = false;
    m_error.clear();
    m_fromCopy = true;
    m_servings = qMax(0, m_recipe.value("servings").toInt());
    m_multiplier = 1.0;
    emit changed();
    emit servingsChanged();
    return true;
}

void Recipes::fetch()
{
    const int generation = ++m_generation;
    m_loading = true;
    m_gone = false;
    m_error.clear();
    m_fromCopy = false;
    emit changed();
    m_api.get(QStringLiteral("/recipes/%1").arg(m_recipeId), QUrlQuery(), [this, generation](const Api::Result &result) {
        if (generation != m_generation)
            return;
        m_loading = false;
        if (result.ok) {
            m_recipe = result.object.value("data").toObject().toVariantMap();
            m_fromCopy = false;
            m_servings = qMax(0, m_recipe.value("servings").toInt());
            m_multiplier = 1.0;
            // A saved recipe's copy takes the freshest detail, what the person keeps on it included.
            if (m_store)
                m_store->update(m_recipe);
        } else if ((result.httpStatus == 0 || !m_api.online()) && openCopy()) {
            // The connection went on the way (spec §8): either no answer came (status 0), or the tunnel answered for
            // an origin that is down, which Api has already taken offline before this handler runs. The copy kept on
            // this device is now shown (fromCopy is true) and no error is reported.
            return;
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
    m_fromCopy = false;
    m_servings = 0;
    m_multiplier = 1.0;
    emit changed();
    emit servingsChanged();
}
