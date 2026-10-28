#include "services/Catalog.h"

#include <QJsonArray>
#include <QJsonObject>

#include <algorithm>


namespace {

// The filters that hold several values, in the order they are sent.
const QStringList kListKeys = {"course", "cuisine", "difficulty", "flavour", "occasion", "alcohol", "avoid"};
const QStringList kIngredientKeys = {"include", "exclude"};
// The server takes up to ten ingredient ids per filter.
constexpr int kIngredientLimit = 10;
// The server takes up to ten cuisine names at once (server/gluttonyRules.py parseFilters); an eleventh is refused.
constexpr int kCuisineLimit = 10;

QString joined(const QVariantList &values)
{
    QStringList parts;
    for (const QVariant &value : values)
        parts << value.toString();
    return parts.join(QLatin1Char(','));
}

QVariantList splitText(const QString &text)
{
    QVariantList values;
    for (const QString &part : text.split(QLatin1Char(','), Qt::SkipEmptyParts))
        if (!part.trimmed().isEmpty())
            values << part.trimmed();
    return values;
}

int ingredientId(const QVariant &value)
{
    return value.toMap().value("id").toInt();
}

} // namespace


Catalog::Catalog(Api &api, Diet &diet, QObject *parent)
    : QObject(parent), m_api(api), m_diet(diet), m_filters(defaultFilters()), m_results(api)
{
    // Switching the diet off, or saving a new one, changes what fits: what is shown is asked for again.
    connect(&m_diet, &Diet::enabledChanged, this, &Catalog::askAgain);
    connect(&m_diet, &Diet::saved, this, &Catalog::askAgain);
}

int Catalog::cuisineLimit()
{
    return kCuisineLimit;
}

QVariantMap Catalog::defaultFilters()
{
    QVariantMap filters;
    filters.insert("kind", QString());
    filters.insert("maxMinutes", 0);
    for (const QString &key : kListKeys)
        filters.insert(key, QVariantList());
    for (const QString &key : kIngredientKeys)
        filters.insert(key, QVariantList());
    filters.insert("q", QString());
    filters.insert("sort", QString());
    return filters;
}

QVariant Catalog::normalised(const QString &key, const QVariant &value)
{
    if (kListKeys.contains(key)) {
        QVariantList values = value.typeId() == QMetaType::QString ? splitText(value.toString()) : value.toList();
        if (key == QLatin1String("difficulty"))
            for (QVariant &item : values)
                item = item.toInt();
        return values;
    }
    if (kIngredientKeys.contains(key))
        return value.toList();
    if (key == QLatin1String("maxMinutes"))
        return value.toInt();
    return value.toString();
}

QUrlQuery Catalog::wireQuery(const QVariantMap &filters, const QString &profileParam)
{
    QUrlQuery query;
    const QString kind = filters.value("kind").toString();
    if (!kind.isEmpty())
        query.addQueryItem("kind", kind);
    const int maxMinutes = filters.value("maxMinutes").toInt();
    if (maxMinutes > 0)
        query.addQueryItem("maxMinutes", QString::number(maxMinutes));
    for (const QString &key : kListKeys) {
        const QVariantList values = filters.value(key).toList();
        if (!values.isEmpty())
            query.addQueryItem(key, joined(values));
    }
    for (const QString &key : kIngredientKeys) {
        QStringList ids;
        for (const QVariant &value : filters.value(key).toList())
            ids << QString::number(ingredientId(value));
        if (!ids.isEmpty())
            query.addQueryItem(key, ids.join(QLatin1Char(',')));
    }
    // The server refuses a search longer than 100 characters, so a pasted line is cut here, for every caller.
    const QString q = filters.value("q").toString().trimmed().left(100).trimmed();
    if (!q.isEmpty())
        query.addQueryItem("q", q);
    const QString sort = filters.value("sort").toString();
    if (!sort.isEmpty())
        query.addQueryItem("sort", sort);
    if (!profileParam.isEmpty())
        query.addQueryItem("profile", profileParam);
    return query;
}

void Catalog::setFilter(const QString &key, const QVariant &value)
{
    if (!m_filters.contains(key))
        return;
    m_filters.insert(key, normalised(key, value));
    // Courses and alcohol belong to food or to drink, so a change of kind starts them again.
    if (key == QLatin1String("kind")) {
        m_filters.insert("course", QVariantList());
        m_filters.insert("alcohol", QVariantList());
    }
    emit filtersChanged();
    apply();
}

void Catalog::toggle(const QString &key, const QVariant &value)
{
    if (!kListKeys.contains(key))
        return;
    QVariantList values = m_filters.value(key).toList();
    const auto at = std::find_if(values.begin(), values.end(),
                                 [&value](const QVariant &item) { return item.toString() == value.toString(); });
    if (at != values.end())
        values.erase(at);
    else if (key == QLatin1String("cuisine") && values.size() >= kCuisineLimit)
        return;
    else
        values.append(value);
    setFilter(key, values);
}

void Catalog::addIngredient(const QString &key, int id, const QString &name)
{
    if (!kIngredientKeys.contains(key) || id <= 0)
        return;
    for (const QString &other : kIngredientKeys)
        for (const QVariant &value : m_filters.value(other).toList())
            if (ingredientId(value) == id)
                return;
    QVariantList values = m_filters.value(key).toList();
    if (values.size() >= kIngredientLimit)
        return;
    values.append(QVariantMap{{"id", id}, {"name", name}});
    m_filters.insert(key, values);
    emit filtersChanged();
    apply();
}

void Catalog::removeIngredient(const QString &key, int id)
{
    if (!kIngredientKeys.contains(key))
        return;
    QVariantList values = m_filters.value(key).toList();
    values.erase(std::remove_if(values.begin(), values.end(),
                                [id](const QVariant &value) { return ingredientId(value) == id; }),
                 values.end());
    m_filters.insert(key, values);
    emit filtersChanged();
    apply();
}

void Catalog::resetFilters()
{
    m_filters = defaultFilters();
    m_title.clear();
    emit filtersChanged();
    apply();
}

void Catalog::openWith(const QVariantMap &preset, const QString &title)
{
    m_filters = defaultFilters();
    for (auto it = preset.cbegin(); it != preset.cend(); ++it)
        if (m_filters.contains(it.key()))
            m_filters.insert(it.key(), normalised(it.key(), it.value()));
    m_title = title;
    emit filtersChanged();
    apply();
}

void Catalog::search(const QString &text)
{
    const QString q = text.trimmed();
    if (q.isEmpty())
        return;
    openWith({{"q", q}, {"sort", "relevance"}}, q);
}

void Catalog::apply()
{
    m_applied = true;
    m_results.run(wireQuery(m_filters, m_diet.profileParam()));
}

void Catalog::askAgain()
{
    if (!m_applied)
        return;
    const QUrlQuery query = wireQuery(m_filters, m_diet.profileParam());
    // The same query with a new profile behind it still finds something else, so it is asked again.
    if (query == m_results.query())
        m_results.reload();
    else
        m_results.run(query);
}

void Catalog::loadOptions()
{
    const int generation = m_generation;
    m_optionsError.clear();
    m_api.get(QStringLiteral("/filters"), QUrlQuery(), [this, generation](const Api::Result &result) {
        if (generation != m_generation)
            return;
        if (result.ok) {
            m_options = result.object.value("data").toObject().toVariantMap();
            m_optionsError.clear();
        } else {
            m_optionsError = reasonOf(result);
        }
        emit optionsChanged();
    });
}

void Catalog::findIngredients(const QString &term)
{
    const QString q = term.trimmed().left(60);
    m_ingredientTerm = q;
    if (q.isEmpty()) {
        m_ingredientMatches.clear();
        emit ingredientMatchesChanged();
        return;
    }
    QUrlQuery query;
    query.addQueryItem("q", q);
    const int generation = m_generation;
    m_api.get(QStringLiteral("/ingredients"), query, [this, generation, q](const Api::Result &result) {
        // Only the answer for what is typed now: a slower answer for an earlier letter never replaces it.
        if (generation != m_generation || q != m_ingredientTerm)
            return;
        m_ingredientMatches = result.ok ? result.object.value("data").toArray().toVariantList() : QVariantList();
        emit ingredientMatchesChanged();
    });
}

void Catalog::quickSearch(const QString &term)
{
    const QString q = term.trimmed();
    m_quickTerm = q;
    if (q.size() < 2) {
        m_quickRecipes.clear();
        m_quickIngredients.clear();
        emit quickChanged();
        return;
    }
    const int generation = m_generation;
    QUrlQuery recipes;
    recipes.addQueryItem("q", q.left(100));
    recipes.addQueryItem("sort", "relevance");
    recipes.addQueryItem("pageSize", "6");
    if (!m_diet.profileParam().isEmpty())
        recipes.addQueryItem("profile", m_diet.profileParam());
    m_api.get(QStringLiteral("/recipes"), recipes, [this, generation, q](const Api::Result &result) {
        if (generation != m_generation || q != m_quickTerm)
            return;
        m_quickRecipes = result.ok
            ? result.object.value("data").toObject().value("recipes").toArray().toVariantList() : QVariantList();
        emit quickChanged();
    });
    QUrlQuery ingredients;
    ingredients.addQueryItem("q", q.left(60));
    m_api.get(QStringLiteral("/ingredients"), ingredients, [this, generation, q](const Api::Result &result) {
        if (generation != m_generation || q != m_quickTerm)
            return;
        m_quickIngredients = result.ok ? result.object.value("data").toArray().toVariantList().mid(0, 5) : QVariantList();
        emit quickChanged();
    });
}

void Catalog::clear()
{
    ++m_generation;
    m_applied = false;
    m_filters = defaultFilters();
    m_title.clear();
    m_options.clear();
    m_optionsError.clear();
    m_results.clear();
    m_ingredientMatches.clear();
    m_ingredientTerm.clear();
    m_quickRecipes.clear();
    m_quickIngredients.clear();
    m_quickTerm.clear();
    emit filtersChanged();
    emit optionsChanged();
    emit ingredientMatchesChanged();
    emit quickChanged();
}
