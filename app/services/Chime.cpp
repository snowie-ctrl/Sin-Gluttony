#include "services/Chime.h"

#include <QUrl>


Chime::Chime(QObject *parent) : QObject(parent)
{
    m_effect.setSource(QUrl(QStringLiteral("qrc:/sounds/chime.wav")));
    m_effect.setVolume(0.8f);
}

void Chime::play()
{
    // Two timers ending in the same moment start it twice; the second start replays it, which still says "done".
    m_effect.play();
}
