#include <QFile>
#include <QTemporaryDir>
#include <QTest>

#include "services/Chime.h"

class TestChime : public QObject
{
    Q_OBJECT

private slots:
    void theChimeLoadsAndSaysSo()
    {
        // The timers' sound must load in this build with Qt Multimedia's DLL present. It does not prove a package
        // carries the multimedia plugin or FFmpeg: release.ps1's file check guards those.
        QTemporaryDir dir;
        const QString file = dir.filePath("chime.txt");
        Chime chime;
        chime.reportTo(file);
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(file), 10000);
        QFile report(file);
        QVERIFY(report.open(QIODevice::ReadOnly));
        QCOMPARE(report.readAll().trimmed(), QByteArray("ready"));
    }
};

QTEST_MAIN(TestChime)
#include "tst_chime.moc"
