#include "services/Home.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QTimeZone>


Home::Home(Api &api, Diet &diet, QObject *parent)
    : QObject(parent), m_api(api), m_diet(diet), m_tz(QString::fromUtf8(QTimeZone::systemTimeZoneId()))
{
    // A new profile, or the profile switched off, changes what fits: what was found before is dropped at once, so
    // nothing chosen under the old profile stays on screen if the new ask fails. A plain Retry keeps what is shown.
    const auto again = [this]() {
        if (!m_answered && !m_loading)
            return;
        m_pick.clear();
        m_picks.clear();
        load();
    };
    connect(&m_diet, &Diet::enabledChanged, this, again);
    connect(&m_diet, &Diet::saved, this, again);
}

QUrlQuery Home::profileQuery() const
{
    QUrlQuery query;
    if (!m_diet.profileParam().isEmpty())
        query.addQueryItem("profile", m_diet.profileParam());
    return query;
}

void Home::load()
{
    QUrlQuery query = profileQuery();
    query.addQueryItem("tz", m_tz);
    const int generation = ++m_loadGeneration;
    m_loading = true;
    emit changed();
    m_api.get(QStringLiteral("/home"), query, [this, generation](const Api::Result &result) {
        if (generation != m_loadGeneration)
            return;
        m_loading = false;
        m_answered = true;
        if (result.ok) {
            const QJsonObject data = result.object.value("data").toObject();
            m_date = data.value("date").toString();
            // A null pick (nothing fits) reads as an empty map.
            m_pick = data.value("pick").toObject().toVariantMap();
            m_picks = data.value("picks").toArray().toVariantList();
            m_error.clear();
        } else {
            m_error = reasonOf(result);
        }
        emit changed();
    });
}

void Home::goOnThen()
{
    if (m_rolling)
        return;
    m_rolling = true;
    emit rollingChanged();
    const int generation = m_rollGeneration;
    m_api.get(QStringLiteral("/random"), profileQuery(), [this, generation](const Api::Result &result) {
        if (generation != m_rollGeneration)
            return;
        m_rolling = false;
        emit rollingChanged();
        if (!result.ok) {
            emit rollFailed(reasonOf(result));
            return;
        }
        const QJsonValue recipe = result.object.value("data").toObject().value("recipe");
        if (recipe.isObject())
            emit picked(recipe.toObject().value("id").toInt());
        else
            emit nothingFits();
    });
}

void Home::clear()
{
    ++m_loadGeneration;
    ++m_rollGeneration;
    m_pick.clear();
    m_picks.clear();
    m_date.clear();
    m_loading = false;
    m_answered = false;
    m_error.clear();
    const bool wasRolling = m_rolling;
    m_rolling = false;
    emit changed();
    if (wasRolling)
        emit rollingChanged();
}
