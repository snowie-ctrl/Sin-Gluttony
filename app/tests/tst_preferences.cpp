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

    void theDefaultsAreEmber()
    {
        Preferences p;
        QCOMPARE(p.backgroundPrimary, QColor(0x0f0f11));
        QCOMPARE(p.backgroundSecondary, QColor(0x17171a));
        QCOMPARE(p.backgroundTertiary, QColor(0x222226));
        QCOMPARE(p.surfaceArt, QColor(0x1c1c1f));
        QCOMPARE(p.borderColor, QColor(0x2c2c31));
        QCOMPARE(p.textPrimary, QColor(0xf4f4f5));
        QCOMPARE(p.textSecondary, QColor(0xb4b4bb));
        QCOMPARE(p.textMuted, QColor(0x7d7d86));
        QCOMPARE(p.accentColor, QColor(0xf27620));
        QCOMPARE(p.accentDeep, QColor(0xe8263f));
        QCOMPARE(p.accentSubtle, QColor(0x2b1d16));
        QCOMPARE(p.dangerColor, QColor(0xf04444));
        QCOMPARE(p.successColor, QColor(0x4fd18b));
        QCOMPARE(p.appFont, QStringLiteral("Tahoma"));
        QCOMPARE(p.headingFont, QStringLiteral("Playfair Display"));
        QCOMPARE(p.cornerRadius, 12);
        QCOMPARE(p.controlRadius, 8);
        QCOMPARE(p.fontSizeDisplay, 26);
        QCOMPARE(p.fontSizeCaption, 12);
        QCOMPARE(p.spacingLarge, 24);
        QCOMPARE(p.units, QStringLiteral("metric"));
    }

    void amberAndRoseAreColoursLikeTheRest()
    {
        Preferences p;
        QCOMPARE(p.property("accentAmber").value<QColor>(), QColor(0xffc24b));
        QCOMPARE(p.property("accentRose").value<QColor>(), QColor(0xff5470));
        QVERIFY(p.defaults().contains("accentAmber"));
        QVERIFY(p.defaults().contains("accentRose"));
        p.setProperty("accentRose", QColor(0x00ff00));
        p.resetColours();
        QCOMPARE(p.property("accentRose").value<QColor>(), QColor(0xff5470));
    }

    void savedValuesAreClampedAndChoicesChecked()
    {
        {
            QSettings settings = file();
            settings.setValue("tileWidth", 5000);
            settings.setValue("units", "imperial-ish");
            settings.setValue("accentColor", "#00ff00");
            settings.setValue("paletteVersion", 2);
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

    void resettingColoursPutsEmberBackAndLeavesTheRest()
    {
        Preferences p;
        p.setProperty("accentColor", QColor(0x00ff00));
        p.setProperty("surfaceArt", QColor(0x123456));
        p.setProperty("units", QStringLiteral("us"));
        p.setProperty("tileWidth", 260);
        p.resetColours();
        QCOMPARE(p.accentColor, QColor(0xf27620));
        QCOMPARE(p.surfaceArt, QColor(0x1c1c1f));
        QCOMPARE(p.units, QStringLiteral("us"));
        QCOMPARE(p.tileWidth, 260);
    }

    void gulaColoursAreClearedOnceAndTheRestKept()
    {
        {
            QSettings settings = file();   // an ini from part 2: no paletteVersion
            settings.setValue("accentColor", "#3a1a0d");
            settings.setValue("backgroundPrimary", "#140c08");
            settings.setValue("units", "us");
            settings.setValue("tileWidth", 260);
            settings.setValue("filterPanelCollapsed", true);
            settings.sync();
        }
        Preferences p;
        QCOMPARE(p.accentColor, QColor(0xf27620));
        QCOMPARE(p.backgroundPrimary, QColor(0x0f0f11));
        QCOMPARE(p.units, QStringLiteral("us"));
        QCOMPARE(p.tileWidth, 260);
        QCOMPARE(p.filterPanelCollapsed, true);
        QSettings after = file();
        QCOMPARE(after.value("paletteVersion").toInt(), 2);
        QVERIFY(!after.contains("accentColor"));
        QVERIFY(!after.contains("backgroundPrimary"));
        QCOMPARE(after.value("units").toString(), QStringLiteral("us"));
    }

    void aColourChangedAfterTheBumpSurvivesARestart()
    {
        {
            Preferences p;                 // a fresh ini: the bump happens here
            p.setProperty("accentRose", QColor(0x00ff00));
        }   // the destructor saves at once
        {
            Preferences p;
            QCOMPARE(p.property("accentRose").value<QColor>(), QColor(0x00ff00));
        }
        Preferences p;                     // and on every start after
        QCOMPARE(p.property("accentRose").value<QColor>(), QColor(0x00ff00));
        QCOMPARE(file().value("paletteVersion").toInt(), 2);
    }

    void aNewerPaletteVersionIsLeftAlone()
    {
        {
            QSettings settings = file();
            settings.setValue("paletteVersion", 3);
            settings.setValue("accentColor", "#123456");
            settings.sync();
        }
        Preferences p;
        QCOMPARE(p.accentColor, QColor(0x123456));
        QCOMPARE(file().value("paletteVersion").toInt(), 3);
    }

    void resetAllLeavesThePaletteVersion()
    {
        Preferences p;
        p.resetAll();
        p.setProperty("units", QStringLiteral("us"));
        p.reset("units");
        QCOMPARE(file().value("paletteVersion").toInt(), 2);
    }
};

// A GUI application: Preferences registers the bundled font, which needs one.
QTEST_MAIN(TestPreferences)
#include "tst_preferences.moc"
