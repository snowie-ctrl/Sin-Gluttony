// Copied from Showtime Showtime/controller/KeepAwake.cpp at 6e44e7a; the include path, and cook mode in the comments.
#include "services/KeepAwake.h"

#ifdef Q_OS_WIN
#include <windows.h>
#endif


KeepAwake::KeepAwake(QObject *parent) : QObject(parent) {}

KeepAwake::~KeepAwake()
{
    // An ES_CONTINUOUS request lasts on the thread until it is cleared, so a
    // KeepAwake destroyed while active (cook mode closing mid-recipe,
    // say) must clear it here, or the machine stays awake for the rest of the
    // process.
    if (m_active)
        apply(false);
}

void KeepAwake::setActive(bool active)
{
    if (active == m_active)
        return;
    m_active = active;
    apply(active);
    emit activeChanged();
}

void KeepAwake::apply(bool active)
{
#ifdef Q_OS_WIN
    // ES_CONTINUOUS makes the request last until it is cleared, rather than
    // nudging the idle timer once. It belongs to the calling thread, which is
    // always the GUI thread here.
    SetThreadExecutionState(active ? (ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
                                   : ES_CONTINUOUS);
#else
    Q_UNUSED(active)
#endif
}
