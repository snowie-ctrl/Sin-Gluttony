#include <QColor>
#include <QSettings>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include "assets/Preferences.h"


class TestPreferences : public QObject
{
    Q_OBJECT

    QTemporaryDir dir;

    static QSettings file()
    {
        return QSettings(QSettings::IniFormat, QSettings::UserScope, QStringLiteral("Gluttony"),
                         QStringLiteral("preferences"));
    }

private slots:
    void initTestCase()
    {
        // Before any Preferences exists, so the owner's real ini is never read or written.
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, dir.path());
    }

    void init()
    {
        QSettings settings = file();
        settings.clear();
        settings.sync();
    }

    void theDefaultsAreGula()
    {
        Preferences p;
        QCOMPARE(p.backgroundPrimary, QColor(0x140c08));
        QCOMPARE(p.backgroundSecondary, QColor(0x22140d));
        QCOMPARE(p.backgroundTertiary, QColor(0x2e1b12));
        QCOMPARE(p.surfaceArt, QColor(0x161312));
        QCOMPARE(p.accentColor, QColor(0xff7a1a));
        QCOMPARE(p.accentDeep, QColor(0xc8212f));
        QCOMPARE(p.accentSubtle, QColor(0x3a1a0d));
        QCOMPARE(p.borderColor, QColor(0x3a2418));
        QCOMPARE(p.textPrimary, QColor(0xfbeee2));
        QCOMPARE(p.textSecondary, QColor(0xd8b9a0));
        QCOMPARE(p.textMuted, QColor(0x9a7a64));
        QCOMPARE(p.dangerColor, QColor(0xe23d3d));
        QCOMPARE(p.successColor, QColor(0x6fbf73));
        QCOMPARE(p.appFont, QStringLiteral("Tahoma"));
        QCOMPARE(p.headingFont, QStringLiteral("Playfair Display"));
        QCOMPARE(p.cornerRadius, 12);
        QCOMPARE(p.controlRadius, 8);
        QCOMPARE(p.fontSizeDisplay, 26);
        QCOMPARE(p.fontSizeCaption, 12);
        QCOMPARE(p.spacingLarge, 24);
        QCOMPARE(p.units, QStringLiteral("metric"));
    }

    void savedValuesAreClampedAndChoicesChecked()
    {
        {
            QSettings settings = file();
            settings.setValue("tileWidth", 5000);
            settings.setValue("units", "imperial-ish");
            settings.setValue("accentColor", "#00ff00");
            settings.sync();
        }
        Preferences p;
        QCOMPARE(p.tileWidth, 320);
        QCOMPARE(p.units, QStringLiteral("metric"));
        QCOMPARE(p.accentColor, QColor(0x00ff00));
    }

    void onlyChangesAreWrittenAndResetPutsTheDefaultBack()
    {
        {
            Preferences p;
            p.setProperty("units", QStringLiteral("us"));
        }   // the destructor saves at once
        QCOMPARE(file().value("units").toString(), QStringLiteral("us"));
        QVERIFY(!file().contains("accentColor"));
        Preferences p;
        QCOMPARE(p.units, QStringLiteral("us"));
        p.reset("units");
        QCOMPARE(p.units, QStringLiteral("metric"));
        QCOMPARE(p.choices("units"), (QStringList{"metric", "us"}));
    }
};

// A GUI application: Preferences registers the bundled font, which needs one.
QTEST_MAIN(TestPreferences)
#include "tst_preferences.moc"
