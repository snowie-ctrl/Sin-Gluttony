// Copied from Showtime Showtime/controller/KeepAwake.h at 6e44e7a; cook mode instead of the player.
#pragma once
#include <QObject>


// Keeps the computer awake while cook mode is open.
//
// A laptop left to its power plan sleeps in the middle of a recipe, because
// cooking involves no input. Cook sets this active while cook mode is open
// and inactive when it closes, so sleep works as usual the rest of the time.
//
// Windows only for now; elsewhere this is inert. The iOS port will map it to
// UIApplication.idleTimerDisabled.
class KeepAwake : public QObject
{
    Q_OBJECT

    Q_PROPERTY(bool active READ active WRITE setActive NOTIFY activeChanged)

public:
    explicit KeepAwake(QObject *parent = nullptr);
    ~KeepAwake() override;

    bool active() const { return m_active; }
    void setActive(bool active);

signals:
    void activeChanged();

private:
    void apply(bool active);

    bool m_active = false;
};
