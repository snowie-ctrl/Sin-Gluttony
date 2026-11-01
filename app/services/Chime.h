#pragma once
#include <QObject>
#include <QSoundEffect>


// The kitchen timer's sound (spec §5: each timer chimes when done): a short sound of the app's own
// (assets/sounds/makeChime.py). With no audio device it is silent, and the timer stack's flash still says it.
class Chime : public QObject
{
    Q_OBJECT

public:
    explicit Chime(QObject *parent = nullptr);
    void play();
    // Writes "ready" or "error" to `file` once the sound has loaded or failed to: release.ps1's check that a package
    // carries Qt Multimedia and its plugin (main.cpp's GLUTTONY_CHIME_CHECK).
    void reportTo(const QString &file);

private:
    QSoundEffect m_effect;
};
