#include <QSignalSpy>
#include <QTest>
#include <QUrlQuery>

#include <memory>

#include "FakeServer.h"
#include "api/Api.h"
#include "services/Catalog.h"
#include "services/Diet.h"

static const QString recipesPath = QStringLiteral("/api/gluttony/recipes");
static const QString ingredientsPath = QStringLiteral("/api/gluttony/ingredients");
static const QString filtersPath = QStringLiteral("/api/gluttony/filters");
static const QString dietPath = QStringLiteral("/api/gluttony/me/diet");
static const QByteArray oneRecipe = R"({"status":"ok","data":{"total":1,"page":1,"pageSize":24,"recipes":[{"id":4,"title":"Stub Spinach Eggs"}]}})";


class TestCatalog : public QObject
{
    Q_OBJECT

    // A new server for every test: a test that ends with requests still on their way (ticks it never waits
    // for) would otherwise have them read by the next test, after its init() has emptied the list it counts.
    std::unique_ptr<FakeServer> server;
    std::unique_ptr<Api> api;
    std::unique_ptr<Diet> diet;
    std::unique_ptr<Catalog> catalog;

    QList<QUrl> to(const QString &path) const
    {
        QList<QUrl> found;
        for (const QUrl &url : server->requests)
            if (url.path() == path)
                found << url;
        return found;
    }

    RecipeQuery *results() const { return qobject_cast<RecipeQuery *>(catalog->results()); }

private slots:
    void init()
    {
        catalog.reset();
        diet.reset();
        api.reset();
        // The new one is listening before the last one goes, so it never takes the port the old requests aimed at.
        server = std::make_unique<FakeServer>();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server->serverPort()));
        diet = std::make_unique<Diet>(*api);
        catalog = std::make_unique<Catalog>(*api, *diet);
        server->responses[recipesPath] = oneRecipe;
    }

    void theWireQueryHoldsOnlyWhatNarrows()
    {
        QVERIFY(Catalog::wireQuery(Catalog::defaultFilters(), QString()).isEmpty());
        QVariantMap f = Catalog::defaultFilters();
        f["kind"] = "food";
        f["maxMinutes"] = 30;
        f["difficulty"] = QVariantList{1};
        f["course"] = QVariantList{"main", "side"};
        f["include"] = QVariantList{QVariantMap{{"id", 3}, {"name", "egg"}}};
        f["q"] = "  eggs ";
        const QUrlQuery q = Catalog::wireQuery(f, "off");
        QCOMPARE(q.queryItemValue("kind"), QStringLiteral("food"));
        QCOMPARE(q.queryItemValue("maxMinutes"), QStringLiteral("30"));
        QCOMPARE(q.queryItemValue("difficulty"), QStringLiteral("1"));
        QCOMPARE(q.queryItemValue("course"), QStringLiteral("main,side"));
        QCOMPARE(q.queryItemValue("include"), QStringLiteral("3"));
        QCOMPARE(q.queryItemValue("q"), QStringLiteral("eggs"));
        QCOMPARE(q.queryItemValue("profile"), QStringLiteral("off"));
        QCOMPARE(q.queryItems().size(), 7);
    }

    void aMoodAsksAtOnceWithItsFilters()
    {
        catalog->openWith({{"kind", "food"}, {"maxMinutes", 30}, {"difficulty", QVariantList{1}}}, "Quick fix");
        QCOMPARE(catalog->title(), QStringLiteral("Quick fix"));
        QTRY_COMPARE(to(recipesPath).size(), 1);
        const QUrlQuery sent(to(recipesPath).last());
        QCOMPARE(sent.queryItemValue("maxMinutes"), QStringLiteral("30"));
        QCOMPARE(sent.queryItemValue("page"), QStringLiteral("1"));
    }

    void aPresetGivenAsTextBecomesAList()
    {
        catalog->openWith({{"course", "dessert,snack"}, {"difficulty", "1,2"}, {"nonsense", "x"}}, "Sweet tooth");
        QCOMPARE(catalog->filters().value("course").toList().size(), 2);
        QCOMPARE(catalog->filters().value("difficulty").toList().first().typeId(), int(QMetaType::Int));
        QVERIFY(!catalog->filters().contains("nonsense"));
    }

    void tickingAddsAValueAndTickingAgainRemovesIt()
    {
        catalog->toggle("cuisine", "Thai");
        QCOMPARE(catalog->filters().value("cuisine").toList(), QVariantList{"Thai"});
        catalog->toggle("cuisine", "Thai");
        QVERIFY(catalog->filters().value("cuisine").toList().isEmpty());
        catalog->toggle("difficulty", 2);
        catalog->toggle("difficulty", QStringLiteral("2"));
        QVERIFY(catalog->filters().value("difficulty").toList().isEmpty());
    }

    void changingKindStartsCourseAndAlcoholAgain()
    {
        catalog->toggle("course", "main");
        catalog->toggle("alcohol", "alcoholic");
        catalog->setFilter("kind", "drink");
        QVERIFY(catalog->filters().value("course").toList().isEmpty());
        QVERIFY(catalog->filters().value("alcohol").toList().isEmpty());
    }

    void anIngredientIsUsedOnceAndAtMostTenAtATime()
    {
        catalog->addIngredient("include", 3, "egg");
        catalog->addIngredient("exclude", 3, "egg");
        QCOMPARE(catalog->filters().value("include").toList().size(), 1);
        QVERIFY(catalog->filters().value("exclude").toList().isEmpty());
        for (int id = 10; id < 30; ++id)
            catalog->addIngredient("include", id, "x");
        QCOMPARE(catalog->filters().value("include").toList().size(), 10);
        catalog->removeIngredient("include", 3);
        QCOMPARE(catalog->filters().value("include").toList().size(), 9);
    }

    void anEleventhCuisineChangesNothingAndAsksNothing()
    {
        // The server refuses more than ten cuisine names, so the eleventh tick is never sent.
        for (int i = 1; i <= 10; ++i)
            catalog->toggle("cuisine", QStringLiteral("Cuisine %1").arg(i));
        QCOMPARE(catalog->filters().value("cuisine").toList().size(), 10);
        QTRY_COMPARE(to(recipesPath).size(), 10);
        QSignalSpy changed(catalog.get(), &Catalog::filtersChanged);
        catalog->toggle("cuisine", "Cuisine 11");
        QCOMPARE(catalog->filters().value("cuisine").toList().size(), 10);
        QVERIFY(!catalog->filters().value("cuisine").toList().contains("Cuisine 11"));
        QCOMPARE(changed.count(), 0);
        QTest::qWait(200);
        QCOMPARE(to(recipesPath).size(), 10);
        // Taking one off still works, and makes room again.
        catalog->toggle("cuisine", "Cuisine 1");
        QCOMPARE(catalog->filters().value("cuisine").toList().size(), 9);
        catalog->toggle("cuisine", "Cuisine 11");
        QCOMPARE(catalog->filters().value("cuisine").toList().size(), 10);
    }

    void switchingTheDietOffAsksAgainWithProfileOff()
    {
        server->responses[dietPath] = R"({"status":"ok","data":{"diets":["vegetarian"],"avoid":[]}})";
        diet->load();
        QTRY_VERIFY(diet->loaded());
        catalog->openWith({}, "Browse");
        QTRY_COMPARE(to(recipesPath).size(), 1);
        diet->setEnabled(false);
        QTRY_COMPARE(to(recipesPath).size(), 2);
        QCOMPARE(QUrlQuery(to(recipesPath).last()).queryItemValue("profile"), QStringLiteral("off"));
    }

    void aNewDietAsksAgainEvenForTheSameFilters()
    {
        catalog->openWith({}, "Browse");
        QTRY_VERIFY(results()->answered());
        server->responses[dietPath] = R"({"status":"ok","data":{"diets":["vegan"],"avoid":[]}})";
        diet->save({"vegan"}, {});
        QTRY_COMPARE(to(recipesPath).size(), 2);
    }

    void nothingIsAskedBeforeTheCatalogIsOpened()
    {
        diet->setEnabled(false);
        QTest::qWait(100);
        QCOMPARE(to(recipesPath).size(), 0);
    }

    void searchingOpensResultsByRelevance()
    {
        catalog->search("  coq ");
        QCOMPARE(catalog->title(), QStringLiteral("coq"));
        QTRY_COMPARE(to(recipesPath).size(), 1);
        const QUrlQuery sent(to(recipesPath).last());
        QCOMPARE(sent.queryItemValue("q"), QStringLiteral("coq"));
        QCOMPARE(sent.queryItemValue("sort"), QStringLiteral("relevance"));
        catalog->search("   ");
        QTest::qWait(100);
        QCOMPARE(to(recipesPath).size(), 1);
    }

    void aLongSearchIsCutToWhatTheServerAccepts()
    {
        catalog->search(QString(130, QLatin1Char('a')));
        QTRY_COMPARE(to(recipesPath).size(), 1);
        QCOMPARE(QUrlQuery(to(recipesPath).last()).queryItemValue("q").size(), 100);
        // The Browse text filter goes the same way, and a cut that ends in a space leaves no trailing space.
        catalog->setFilter("q", QString(99, QLatin1Char('b')) + QStringLiteral(" cc"));
        QTRY_COMPARE(to(recipesPath).size(), 2);
        QCOMPARE(QUrlQuery(to(recipesPath).last()).queryItemValue("q"), QString(99, QLatin1Char('b')));
    }

    void quickSearchNeedsTwoLetters()
    {
        catalog->quickSearch("e");
        QTest::qWait(100);
        QCOMPARE(server->requests.size(), 0);
        server->responses[ingredientsPath] = R"({"status":"ok","data":[{"id":301,"name":"egg"}]})";
        catalog->quickSearch("eg");
        QTRY_COMPARE(catalog->quickRecipes().size(), 1);
        QTRY_COMPARE(catalog->quickIngredients().size(), 1);
        QCOMPARE(QUrlQuery(to(recipesPath).last()).queryItemValue("pageSize"), QStringLiteral("6"));
        catalog->quickSearch("e");
        QVERIFY(catalog->quickRecipes().isEmpty() && catalog->quickIngredients().isEmpty());
    }

    void aSlowAnswerForAnEarlierWordIsDropped()
    {
        server->queued[ingredientsPath] = {R"({"status":"ok","data":[{"id":1,"name":"ch"}]})",
                                           R"({"status":"ok","data":[{"id":2,"name":"cheese"}]})"};
        server->holdNext[ingredientsPath] = 1;
        catalog->findIngredients("ch");
        QTRY_COMPARE(to(ingredientsPath).size(), 1);
        catalog->findIngredients("cheese");
        QTRY_COMPARE(catalog->ingredientMatches().size(), 1);
        server->releaseHeld();
        QTest::qWait(200);
        QCOMPARE(catalog->ingredientMatches().first().toMap().value("id").toInt(), 2);
    }

    void optionsLoadAndAFailureSaysWhy()
    {
        server->responses[filtersPath] = R"({"status":"ok","data":{"kinds":[{"value":"food","count":3}],"avoid":["peanut"]}})";
        catalog->loadOptions();
        QTRY_VERIFY(!catalog->options().isEmpty());
        QCOMPARE(catalog->options().value("avoid").toList().first().toString(), QStringLiteral("peanut"));
        server->responses[filtersPath] = R"({"status":"error","message":"server error"})";
        server->statuses[filtersPath] = 500;
        catalog->loadOptions();
        QTRY_COMPARE(catalog->optionsError(), QStringLiteral("server error"));
    }

    void clearingStartsAgainFromNothing()
    {
        catalog->openWith({{"kind", "drink"}}, "Bottoms up");
        QTRY_VERIFY(results()->answered());
        catalog->clear();
        QCOMPARE(catalog->filters(), Catalog::defaultFilters());
        QVERIFY(catalog->title().isEmpty());
        QCOMPARE(results()->count(), 0);
    }
};

QTEST_GUILESS_MAIN(TestCatalog)
#include "tst_catalog.moc"
