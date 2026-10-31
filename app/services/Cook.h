#pragma once
#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QString>
#include <QTimer>
#include <QVariantList>
#include <QVariantMap>

#include <functional>

#include "services/KeepAwake.h"

class AccountStore;


// The open cook session (spec §5): the recipe being cooked, its current step and the ingredient lines ticked off,
// and the kitchen timers. While cook mode is open the screen is kept on (KeepAwake). The step and ticks are kept for
// each recipe for 12 hours, per device, in the account's folder (cook.json), so coming back to a recipe resumes it.
// Timers outlive cook mode: they keep counting, shown in the rail, and a finished one stays until it is dismissed.
class Cook : public QObject
{
    Q_OBJECT

    Q_PROPERTY(bool active READ active NOTIFY activeChanged)
    Q_PROPERTY(int recipeId READ recipeId NOTIFY activeChanged)
    // The detail cook mode opened with (Recipes' recipe, or its offline copy).
    Q_PROPERTY(QVariantMap recipe READ recipe NOTIFY activeChanged)
    Q_PROPERTY(int step READ step NOTIFY stepChanged)
    Q_PROPERTY(int stepCount READ stepCount NOTIFY activeChanged)
    // The ingredient lines ticked off, by their index in the recipe's ingredients, in the order ticked.
    Q_PROPERTY(QVariantList ticks READ ticks NOTIFY ticksChanged)
    // [{id, label, seconds, remaining, done}], oldest first; remaining is in whole seconds, rounded up.
    Q_PROPERTY(QVariantList timers READ timers NOTIFY timersChanged)
    Q_PROPERTY(bool awake READ awake NOTIFY activeChanged)

public:
    static constexpr qint64 ResumeMs = 12LL * 60 * 60 * 1000;

    explicit Cook(QObject *parent = nullptr);

    // Where cook.json lives: the open account's folder, which follows sign-in and sign-out.
    void setStore(AccountStore *store) { m_store = store; }
    // Milliseconds since the epoch; tests move it forward instead of waiting.
    void setClock(std::function<qint64()> clock) { m_clock = std::move(clock); }

    bool active() const { return m_active; }
    int recipeId() const { return m_recipeId; }
    QVariantMap recipe() const { return m_recipe; }
    int step() const { return m_step; }
    int stepCount() const { return int(m_recipe.value("steps").toList().size()); }
    QVariantList ticks() const;
    QVariantList timers() const;
    bool awake() const { return m_keepAwake.active(); }

    // Opens cook mode on a recipe, where it was left if that was less than 12 hours ago.
    Q_INVOKABLE void open(const QVariantMap &recipe);
    Q_INVOKABLE void close();
    Q_INVOKABLE void goTo(int step);
    Q_INVOKABLE void next() { goTo(m_step + 1); }
    Q_INVOKABLE void previous() { goTo(m_step - 1); }
    Q_INVOKABLE void toggleTick(int line);
    // A countdown of `seconds` (more than 0), named `label` for the rail. Returns its id, 0 when none was started.
    Q_INVOKABLE int startTimer(int seconds, const QString &label);
    // Stops a running timer, or puts a finished one away.
    Q_INVOKABLE void dismissTimer(int timerId);
    // Reads the clock: timers that reached zero say so. The tick calls it four times a second while one runs.
    void update();
    // Signing out: cook mode closes and the timers go; what was kept stays in the folder signing out deletes.
    void clear();

signals:
    void activeChanged();
    void stepChanged();
    void ticksChanged();
    void timersChanged();
    // Cook mode opened on this recipe, which is then kept for use offline (RecipeStore::keepForCooking).
    void opened(const QVariantMap &recipe);
    // A timer reached zero: the chime plays once for each.
    void timerDone(int timerId, const QString &label);

private:
    struct Timer
    {
        int id;
        QString label;
        int seconds;
        qint64 endsAt;
        bool done;
    };

    void save();
    QJsonObject readKept() const;
    QString keptFile() const;
    bool anyRunning() const;
    void announceTimers();

    AccountStore *m_store = nullptr;
    std::function<qint64()> m_clock;
    KeepAwake m_keepAwake;
    bool m_active = false;
    int m_recipeId = 0;
    QVariantMap m_recipe;
    int m_step = 0;
    QList<int> m_ticks;
    QList<Timer> m_timers;
    int m_nextTimerId = 1;
    QTimer m_tick;
    // The timers as last announced: timersChanged is said when a shown second changes, not four times a second.
    QVariantList m_shown;
};
