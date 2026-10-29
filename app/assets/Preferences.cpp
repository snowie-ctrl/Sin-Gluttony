// Copied from Pageturner Pageturner/assets/Preferences.cpp at ad9342e; Gluttony's limits and choices, its own ini
// name, the bundled Playfair Display; no per-series settings; resetColours is new.
#include "Preferences.h"

#include <QDebug>
#include <QFile>
#include <QFontDatabase>
#include <QHash>
#include <QMetaProperty>
#include <QSettings>

namespace {

struct Limit { double min; double max; double step; };

// Ranges for everything numeric. The settings page builds its sliders from
// these, and anything read back from disk is clamped to them.
const QHash<QString, Limit> &limitTable()
{
    static const QHash<QString, Limit> table = {
        { "cornerRadius",  { 0, 24, 1 } },
        { "controlRadius", { 0, 16, 1 } },
        { "tileWidth",     { 140, 320, 10 } },
    };
    return table;
}

// The values each text preference may take, first one not necessarily the default.
const QHash<QString, QStringList> &choiceTable()
{
    static const QHash<QString, QStringList> table = {
        { "units", { "metric", "us" } },
    };
    return table;
}

// The properties that are preferences: everything Preferences declares
// itself (not QObject's objectName) that can be written.
QList<QMetaProperty> preferenceProperties(const QMetaObject *meta)
{
    QList<QMetaProperty> result;
    for (int i = meta->propertyOffset(); i < meta->propertyCount(); ++i) {
        const QMetaProperty property = meta->property(i);
        if (property.isWritable())
            result.append(property);
    }
    return result;
}

// Colours are stored as text, so the file stays readable and editable
// rather than holding QSettings' binary @Variant blobs.
QVariant toStored(const QVariant &value)
{
    if (value.metaType().id() == QMetaType::QColor)
        return value.value<QColor>().name(QColor::HexRgb);
    return value;
}

bool sameValue(const QVariant &a, const QVariant &b)
{
    if (a.metaType().id() == QMetaType::Double)
        return qFuzzyCompare(1.0 + a.toDouble(), 1.0 + b.toDouble());
    return toStored(a) == toStored(b);
}

QSettings openSettings()
{
    // An ini under %APPDATA%\Gluttony rather than the registry: one file the
    // user can find, read, back up, or delete to start over.
    return QSettings(QSettings::IniFormat, QSettings::UserScope,
                     QStringLiteral("Gluttony"), QStringLiteral("preferences"));
}

} // namespace


Preferences::Preferences(QObject *parent) : QObject(parent)
{
    // The bundled heading font. Tests have no resources, so a miss there is expected.
    if (QFontDatabase::addApplicationFont(":/fonts/PlayfairDisplay/PlayfairDisplay.ttf") == -1)
        qDebug() << "[preferences] Playfair Display not loaded (fine in tests, which have no resources)";

    for (const QMetaProperty &property : preferenceProperties(metaObject()))
        m_defaults.insert(QString::fromLatin1(property.name()), property.read(this));

    load();

    // A slider drag changes a value dozens of times a second; the file is
    // written once it settles.
    m_saveTimer.setSingleShot(true);
    m_saveTimer.setInterval(400);
    connect(&m_saveTimer, &QTimer::timeout, this, &Preferences::save);

    // Every preference's change signal, found rather than listed, so a new
    // preference is saved without anyone remembering to wire it up.
    const QMetaMethod saveSlot = metaObject()->method(
        metaObject()->indexOfSlot("scheduleSave()"));
    for (const QMetaProperty &property : preferenceProperties(metaObject())) {
        if (property.hasNotifySignal())
            connect(this, property.notifySignal(), this, saveSlot, Qt::UniqueConnection);
    }
}

Preferences::~Preferences()
{
    // A change made in the last moment before closing still lands.
    if (m_saveTimer.isActive())
        save();
}

QString Preferences::storagePath() const
{
    return openSettings().fileName();
}

QVariantMap Preferences::limits(const QString &key) const
{
    const auto it = limitTable().constFind(key);
    if (it == limitTable().constEnd())
        return {};
    return { { "min", it->min }, { "max", it->max }, { "step", it->step } };
}

QStringList Preferences::choices(const QString &key) const
{
    return choiceTable().value(key);
}

QVariant Preferences::clamped(const QString &key, const QVariant &value) const
{
    const auto choice = choiceTable().constFind(key);
    if (choice != choiceTable().constEnd())
        return choice->contains(value.toString()) ? value : m_defaults.value(key);

    const auto it = limitTable().constFind(key);
    if (it == limitTable().constEnd())
        return value;
    const double bounded = qBound(it->min, value.toDouble(), it->max);
    if (value.metaType().id() == QMetaType::Int)
        return QVariant(qRound(bounded));
    return QVariant(bounded);
}

void Preferences::reset(const QString &key)
{
    const int index = metaObject()->indexOfProperty(key.toLatin1().constData());
    if (index < 0 || !m_defaults.contains(key))
        return;
    metaObject()->property(index).write(this, m_defaults.value(key));
}

void Preferences::resetAll()
{
    for (auto it = m_defaults.constBegin(); it != m_defaults.constEnd(); ++it)
        reset(it.key());
}

void Preferences::resetColours()
{
    // Found rather than listed, so a colour token added later is reset too.
    for (const QMetaProperty &property : preferenceProperties(metaObject()))
        if (property.metaType().id() == QMetaType::QColor)
            reset(QString::fromLatin1(property.name()));
}

void Preferences::scheduleSave()
{
    m_saveTimer.start();
}

void Preferences::load()
{
    QSettings settings = openSettings();

    for (const QMetaProperty &property : preferenceProperties(metaObject())) {
        const QString key = QString::fromLatin1(property.name());
        if (!settings.contains(key))
            continue;
        const QVariant stored = settings.value(key);

        // A font that has since been uninstalled would otherwise fall back
        // to whatever Windows picks.
        if (key == QLatin1String("appFont")) {
            const QString family = stored.toString();
            if (QFontDatabase::hasFamily(family))
                appFont = family;
            else
                qWarning() << "[preferences] font not installed, using the default:" << family;
            continue;
        }

        // Anything that does not read back as the right type is ignored and
        // the default stays, rather than a bad line breaking the app.
        switch (property.metaType().id()) {
        case QMetaType::QColor: {
            const QColor color = QColor::fromString(stored.toString());
            if (color.isValid())
                property.write(this, color);
            break;
        }
        default: {
            QVariant value = stored;
            if (value.convert(property.metaType()))
                property.write(this, clamped(key, value));
            break;
        }
        }
    }
}

void Preferences::save()
{
    m_saveTimer.stop();
    QSettings settings = openSettings();

    // Only what differs from the defaults is written. The file then holds
    // exactly what the user changed, and a default improved in code still
    // reaches everyone who never touched that setting.
    for (const QMetaProperty &property : preferenceProperties(metaObject())) {
        const QString key = QString::fromLatin1(property.name());
        const QVariant value = property.read(this);
        if (sameValue(value, m_defaults.value(key)))
            settings.remove(key);
        else
            settings.setValue(key, toStored(value));
    }

    settings.sync();
    if (settings.status() != QSettings::NoError)
        qWarning() << "[preferences] could not save to" << settings.fileName();
}
