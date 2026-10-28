#include "services/Diet.h"

#include <QJsonArray>
#include <QUrlQuery>


namespace {

QStringList stringsOf(const QJsonValue &value)
{
    QStringList strings;
    for (const QJsonValue &item : value.toArray())
        strings << item.toString();
    return strings;
}

} // namespace


Diet::Diet(Api &api, QObject *parent) : QObject(parent), m_api(api) {}

void Diet::setEnabled(bool enabled)
{
    if (enabled == m_enabled)
        return;
    m_enabled = enabled;
    emit enabledChanged();
}

void Diet::apply(const QJsonObject &data)
{
    m_diets = stringsOf(data.value("diets"));
    m_avoid = stringsOf(data.value("avoid"));
    m_loaded = true;
}

void Diet::load()
{
    const int generation = m_generation;
    m_api.get(QStringLiteral("/me/diet"), QUrlQuery(), [this, generation](const Api::Result &result) {
        if (generation != m_generation)
            return;
        if (result.ok) {
            apply(result.object.value("data").toObject());
            m_error.clear();
        } else {
            m_error = reasonOf(result);
        }
        emit changed();
    });
}

void Diet::save(const QStringList &diets, const QStringList &avoid)
{
    if (m_saving)
        return;
    m_saving = true;
    m_error.clear();
    emit changed();
    const int generation = m_generation;
    const QJsonObject body{{"diets", QJsonArray::fromStringList(diets)}, {"avoid", QJsonArray::fromStringList(avoid)}};
    m_api.post(QStringLiteral("/me/diet"), body, [this, generation](const Api::Result &result) {
        if (generation != m_generation)
            return;
        m_saving = false;
        if (!result.ok) {
            m_error = reasonOf(result);
            emit changed();
            return;
        }
        apply(result.object.value("data").toObject());
        // A profile just chosen is meant to apply.
        const bool wasOff = !m_enabled;
        m_enabled = true;
        emit changed();
        if (wasOff)
            emit enabledChanged();
        emit saved();
    });
}

void Diet::clearError()
{
    if (m_error.isEmpty())
        return;
    m_error.clear();
    emit changed();
}

void Diet::clear()
{
    ++m_generation;
    m_diets.clear();
    m_avoid.clear();
    m_loaded = false;
    m_saving = false;
    m_error.clear();
    const bool wasOff = !m_enabled;
    m_enabled = true;
    emit changed();
    if (wasOff)
        emit enabledChanged();
}
