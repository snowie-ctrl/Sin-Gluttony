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

private:
    QSoundEffect m_effect;
};
