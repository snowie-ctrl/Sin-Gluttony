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
        // The timers' sound must load wherever the app runs; a package without Qt Multimedia's plugin says "error".
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
