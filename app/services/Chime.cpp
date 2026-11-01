#include "services/Chime.h"

#include <QFile>
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

void Chime::reportTo(const QString &file)
{
    const auto report = [this, file]() {
        const QSoundEffect::Status status = m_effect.status();
        if (status != QSoundEffect::Ready && status != QSoundEffect::Error)
            return false;
        QFile out(file);
        if (out.open(QIODevice::WriteOnly | QIODevice::Truncate))
            out.write(status == QSoundEffect::Ready ? "ready\n" : "error\n");
        return true;
    };
    if (report())
        return;
    auto *once = new QMetaObject::Connection;
    *once = connect(&m_effect, &QSoundEffect::statusChanged, this, [report, once]() {
        if (report()) {
            QObject::disconnect(*once);
            delete once;
        }
    });
}
