#include "services/Cook.h"

#include <QDateTime>
#include <QJsonArray>

#include <algorithm>

#include "services/AccountStore.h"


Cook::Cook(QObject *parent)
    : QObject(parent), m_clock([]() { return QDateTime::currentMSecsSinceEpoch(); })
{
    m_tick.setInterval(250);
    connect(&m_tick, &QTimer::timeout, this, &Cook::update);
}

QVariantList Cook::ticks() const
{
    QVariantList out;
    for (const int line : m_ticks)
        out << line;
    return out;
}

QVariantList Cook::timers() const
{
    QVariantList out;
    const qint64 now = m_clock();
    for (const Timer &timer : m_timers) {
        const qint64 left = timer.done ? 0 : qMax<qint64>(0, timer.endsAt - now);
        out << QVariantMap{{"id", timer.id}, {"label", timer.label}, {"seconds", timer.seconds},
                           {"remaining", int((left + 999) / 1000)}, {"done", timer.done}};
    }
    return out;
}

QString Cook::keptFile() const
{
    return m_store ? m_store->file(QStringLiteral("cook.json")) : QString();
}

QJsonObject Cook::readKept() const
{
    const QString file = keptFile();
    return file.isEmpty() ? QJsonObject() : AccountStore::readJson(file);
}

void Cook::open(const QVariantMap &recipe)
{
    const int id = recipe.value("id").toInt();
    if (id <= 0)
        return;
    m_recipe = recipe;
    m_recipeId = id;
    m_step = 0;
    m_ticks.clear();
    // Back within 12 hours: where the cook left off, within what this recipe now has.
    const QJsonObject kept = readKept().value(QString::number(id)).toObject();
    if (!kept.isEmpty() && m_clock() - qint64(kept.value("savedAt").toDouble()) < ResumeMs) {
        m_step = qBound(0, kept.value("step").toInt(), qMax(0, stepCount() - 1));
        const int lines = int(recipe.value("ingredients").toList().size());
        for (const QJsonValue &value : kept.value("ticks").toArray()) {
            const int line = value.toInt(-1);
            if (line >= 0 && line < lines && !m_ticks.contains(line))
                m_ticks << line;
        }
    }
    m_active = true;
    updateAwake();
    emit activeChanged();
    emit stepChanged();
    emit ticksChanged();
    emit opened(recipe);
}

void Cook::close()
{
    if (!m_active)
        return;
    save();
    m_active = false;
    updateAwake();
    emit activeChanged();
}

void Cook::goTo(int step)
{
    if (!m_active)
        return;
    const int bounded = qBound(0, step, qMax(0, stepCount() - 1));
    if (bounded == m_step)
        return;
    m_step = bounded;
    save();
    emit stepChanged();
}

void Cook::toggleTick(int line)
{
    if (!m_active || line < 0 || line >= m_recipe.value("ingredients").toList().size())
        return;
    if (!m_ticks.removeOne(line))
        m_ticks << line;
    save();
    emit ticksChanged();
}

void Cook::save()
{
    const QString file = keptFile();
    if (file.isEmpty() || m_recipeId <= 0)
        return;
    QJsonObject kept = readKept();
    // A place older than 12 hours would never be resumed, so it goes rather than piling up.
    const qint64 now = m_clock();
    for (const QString &key : kept.keys())
        if (now - qint64(kept.value(key).toObject().value("savedAt").toDouble()) >= ResumeMs)
            kept.remove(key);
    QJsonArray ticks;
    for (const int line : m_ticks)
        ticks.append(line);
    kept.insert(QString::number(m_recipeId),
                QJsonObject{{"step", m_step}, {"ticks", ticks}, {"savedAt", double(now)}});
    AccountStore::writeJson(file, kept);
}

bool Cook::anyRunning() const
{
    return std::any_of(m_timers.cbegin(), m_timers.cend(), [](const Timer &timer) { return !timer.done; });
}

void Cook::updateAwake()
{
    // A timer that is counting needs the machine awake after cook mode closes too: asleep, it would not chime.
    const bool wanted = m_active || anyRunning();
    if (wanted == m_keepAwake.active())
        return;
    m_keepAwake.setActive(wanted);
    emit awakeChanged();
}

void Cook::announceTimers()
{
    m_shown = timers();
    emit timersChanged();
}

int Cook::startTimer(int seconds, const QString &label)
{
    if (seconds <= 0)
        return 0;
    const int id = m_nextTimerId++;
    m_timers.append({id, label, seconds, m_clock() + qint64(seconds) * 1000, false});
    m_tick.start();
    updateAwake();
    announceTimers();
    return id;
}

void Cook::dismissTimer(int timerId)
{
    const auto found = std::find_if(m_timers.begin(), m_timers.end(),
                                    [timerId](const Timer &timer) { return timer.id == timerId; });
    if (found == m_timers.end())
        return;
    m_timers.erase(found);
    if (!anyRunning())
        m_tick.stop();
    updateAwake();
    announceTimers();
}

void Cook::update()
{
    const qint64 now = m_clock();
    QList<Timer> finished;
    for (Timer &timer : m_timers) {
        if (!timer.done && now >= timer.endsAt) {
            timer.done = true;
            finished << timer;
        }
    }
    if (!anyRunning())
        m_tick.stop();
    updateAwake();
    if (timers() != m_shown)
        announceTimers();
    for (const Timer &timer : finished)
        emit timerDone(timer.id, timer.label);
}

void Cook::clear()
{
    const bool wasActive = m_active;
    m_active = false;
    m_recipe.clear();
    m_recipeId = 0;
    m_step = 0;
    m_ticks.clear();
    m_timers.clear();
    m_tick.stop();
    updateAwake();
    announceTimers();
    if (wasActive)
        emit activeChanged();
    emit stepChanged();
    emit ticksChanged();
}
