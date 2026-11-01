#include <QDir>
#include <QFile>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include "services/AccountStore.h"


class TestAccountStore : public QObject
{
    Q_OBJECT

private slots:
    void anAccountLivesInItsOwnFolder()
    {
        QTemporaryDir root;
        AccountStore store(root.path());
        QSignalSpy changed(&store, &AccountStore::changed);
        store.open(7, "ann");
        QCOMPARE(store.uid(), 7);
        QCOMPARE(store.dir(), root.path() + "/accounts/7");
        QCOMPARE(store.recipeFile(12), root.path() + "/accounts/7/recipes/12.json");
        QVERIFY(QDir(store.recipesDir()).exists());
        QCOMPARE(AccountStore::readJson(store.file("account.json")).value("username").toString(), QStringLiteral("ann"));
        QCOMPARE(AccountStore::readJson(root.path() + "/accounts/last.json").value("UID").toInt(), 7);
        QCOMPARE(changed.count(), 1);
        store.open(7, "annie");     // a new username is not a change of account
        QCOMPARE(changed.count(), 1);
    }

    void noAccountMeansNoPaths()
    {
        QTemporaryDir root;
        AccountStore store(root.path());
        QCOMPARE(store.uid(), -1);
        QVERIFY(store.dir().isEmpty() && store.recipesDir().isEmpty() && store.recipeFile(1).isEmpty());
    }

    void theLastAccountOpensOfflineOnlyWithASavedRecipe()
    {
        QTemporaryDir root;
        {
            AccountStore store(root.path());
            store.open(7, "ann");
            QVERIFY(store.offlineAccount().isEmpty());
            QVERIFY(AccountStore::writeJson(store.recipeFile(12), QJsonObject{{"id", 12}}));
            store.close();
        }
        AccountStore again(root.path());
        const QVariantMap account = again.offlineAccount();
        QCOMPARE(account.value("UID").toInt(), 7);
        QCOMPARE(account.value("username").toString(), QStringLiteral("ann"));
        again.forgetLast();
        QVERIFY(again.offlineAccount().isEmpty());
    }

    void wipingSaysSoFirstThenRemovesEverything()
    {
        QTemporaryDir root;
        AccountStore store(root.path());
        store.open(7, "ann");
        QVERIFY(AccountStore::writeJson(store.recipeFile(12), QJsonObject{{"id", 12}}));
        bool folderStillThere = false;
        connect(&store, &AccountStore::changed, this, [&]() { folderStillThere = QDir(root.path() + "/accounts/7").exists(); });
        store.wipe();
        QVERIFY(folderStillThere);
        QVERIFY(!QDir(root.path() + "/accounts/7").exists());
        QVERIFY(!QFile::exists(root.path() + "/accounts/last.json"));
        QCOMPARE(store.uid(), -1);
    }

    void wipingNamesTheAccountItWiped()
    {
        QTemporaryDir root;
        AccountStore store(root.path());
        QSignalSpy wiped(&store, &AccountStore::wiped);
        store.open(7, "ann");
        store.wipe();
        QCOMPARE(wiped.count(), 1);
        QCOMPARE(wiped.first().first().toInt(), 7);
        store.open(8, "bob");
        store.close();
        store.wipeAccount(8);
        QCOMPARE(wiped.count(), 2);
        QCOMPARE(wiped.last().first().toInt(), 8);
    }

    void aClosedAccountCanStillBeWiped()
    {
        QTemporaryDir root;
        AccountStore store(root.path());
        store.open(7, "ann");
        store.close();
        QVERIFY(QDir(root.path() + "/accounts/7").exists());
        store.wipeAccount(7);
        QVERIFY(!QDir(root.path() + "/accounts/7").exists());
    }

    void aPendingSignOutOutlivesTheWipeAndTheProgram()
    {
        QTemporaryDir root;
        {
            AccountStore store(root.path());
            store.open(7, "ann");
            store.setPendingLogout(7);
            store.wipe();
        }
        AccountStore again(root.path());
        QCOMPARE(again.pendingLogout(), 7);
        again.clearPendingLogout();
        QCOMPARE(again.pendingLogout(), -1);
        QVERIFY(!QFile::exists(root.path() + "/accounts/pending-logout.json"));
    }
};

QTEST_GUILESS_MAIN(TestAccountStore)
#include "tst_accountstore.moc"
