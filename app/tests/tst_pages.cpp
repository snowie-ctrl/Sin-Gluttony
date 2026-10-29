#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQuickItem>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QSettings>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUrlQuery>
#include <QtQml/QQmlExtensionPlugin>

#include <algorithm>
#include <memory>

#include "FakeServer.h"
#include "api/Api.h"
#include "assets/Preferences.h"
#include "services/AccountStore.h"
#include "services/Catalog.h"
#include "services/Diet.h"
#include "services/Home.h"
#include "services/Nav.h"
#include "services/Recipes.h"
#include "services/Saved.h"
#include "services/Session.h"
#include "services/Wiring.h"

Q_IMPORT_QML_PLUGIN(GluttonyPlugin)

static QString path(const char *route)
{
    return QStringLiteral("/api/gluttony") + QLatin1String(route);
}

static const QByteArray signedIn = R"({"status":"ok","UID":7,"username":"stub","token":"tok"})";
static const QByteArray noDiet = R"({"status":"ok","data":{"diets":[],"avoid":[]}})";
static const QByteArray emptyHome = R"({"status":"ok","data":{"date":"2026-10-27","pick":null,"picks":[]}})";
static const QByteArray options = R"({"status":"ok","data":{"kinds":[{"value":"food","count":3}],
  "courses":[{"value":"main","count":2},{"value":"cocktail","count":1}],"cuisines":[{"value":"French","count":2}],
  "difficulties":[],"flavours":[{"value":"savoury","count":3}],"occasions":[{"value":"party","count":2}],
  "diets":[],"avoid":["meat","peanut"]}})";


// The real Main.qml, NavShell and pages over the real services, the server faked. Clicks go to the offscreen
// window only. Each page task adds its cases here.
class TestPages : public QObject
{
    Q_OBJECT

    QTemporaryDir dir;
    std::unique_ptr<FakeServer> server;
    std::unique_ptr<Preferences> preferences;
    std::unique_ptr<Api> api;
    std::unique_ptr<Nav> nav;
    std::unique_ptr<AccountStore> accounts;
    std::unique_ptr<Session> session;
    std::unique_ptr<Diet> diet;
    std::unique_ptr<Catalog> catalog;
    std::unique_ptr<Home> home;
    std::unique_ptr<Recipes> recipes;
    std::unique_ptr<Saved> saved;
    // Declared last, so it is destroyed first: pages go before the services they call.
    std::unique_ptr<QQmlApplicationEngine> engine;

    QQuickWindow *window() const
    {
        return engine ? qobject_cast<QQuickWindow *>(engine->rootObjects().value(0)) : nullptr;
    }

    // Popups sit in the window's overlay, a child of the window's root item beside the shell, so the walk starts
    // at that root item.
    static QQuickItem *findIn(QQuickItem *root, const QString &name, bool visibleOnly = false)
    {
        QList<QQuickItem *> pending{root};
        while (!pending.isEmpty()) {
            QQuickItem *item = pending.takeFirst();
            if (item->objectName() == name && (!visibleOnly || item->isVisible()))
                return item;
            pending += item->childItems();
        }
        return nullptr;
    }

    QQuickItem *find(const QString &name) const
    {
        return window() ? findIn(window()->contentItem(), name) : nullptr;
    }

    QQuickItem *findVisible(const QString &name) const
    {
        return window() ? findIn(window()->contentItem(), name, true) : nullptr;
    }

    void click(QQuickItem *item)
    {
        QVERIFY(item);
        // A page lays itself out in the frame after it appears, so an item found straight away can still be where it
        // was before that frame. Without this wait a click now and then landed beside its target on a busy machine.
        QSignalSpy framed(window(), &QQuickWindow::frameSwapped);
        window()->update();
        framed.wait(250);
        const QPointF centre = item->mapToScene(QPointF(item->width() / 2, item->height() / 2));
        QTest::mouseClick(window(), Qt::LeftButton, Qt::NoModifier, centre.toPoint());
    }

    // The body of the last request to a route that carried one (a GET has none).
    QJsonObject lastBodyTo(const char *route) const
    {
        for (int i = server->requests.size() - 1; i >= 0; --i)
            if (server->requests[i].path() == path(route) && !server->bodies[i].isEmpty())
                return QJsonDocument::fromJson(server->bodies[i]).object();
        return {};
    }

    QList<QUrl> requestsTo(const char *route) const
    {
        QList<QUrl> found;
        for (const QUrl &url : server->requests)
            if (url.path() == path(route))
                found << url;
        return found;
    }

    // QTest has no keyClicks for a window, so the letters go one by one.
    void type(const QString &text)
    {
        for (const QChar ch : text) {
            if (ch == QLatin1Char(' '))
                QTest::keyClick(window(), Qt::Key_Space);
            else
                QTest::keyClick(window(), ch.toLatin1());
        }
    }

    // The app as main.cpp builds it; the device signs itself in at once unless a test answers otherwise.
    void start()
    {
        engine = std::make_unique<QQmlApplicationEngine>();
        QQmlContext *context = engine->rootContext();
        context->setContextProperty("Preferences", preferences.get());
        context->setContextProperty("Nav", nav.get());
        context->setContextProperty("Session", session.get());
        context->setContextProperty("Diet", diet.get());
        context->setContextProperty("Catalog", catalog.get());
        context->setContextProperty("Home", home.get());
        context->setContextProperty("Recipes", recipes.get());
        context->setContextProperty("Saved", saved.get());
        engine->loadFromModule("Gluttony", "Main");
        QVERIFY(window());
        // Tall enough that the whole filter panel and the recipe page's first screen are on it, so clicks land.
        window()->resize(1600, 1600);
        session->identifyDevice();
    }

    // Opens fixture recipe 1 on the recipe page. A helper, not a test, so it sits above the slots.
    void openRecipeOne()
    {
        // The title holds ")" followed by a quote, so the literal needs its own delimiter.
        server->responses[path("/recipes/1")] = R"json({"status":"ok","data":{"id":1,"kind":"food","title":"Stub Coq au Vin",
          "course":"main","cuisine":"French","servings":4,"servingsFrom":"source","totalMinutes":105,"timeFrom":"rule",
          "difficulty":2,"difficultyFrom":"rule","hasImage":false,"source":"mealdb","sourceUrl":null,"licence":"TheMealDB",
          "credit":"Recipe data and imagery: TheMealDB","imageCredit":null,"videoUrl":null,
          "ingredients":[
            {"line":"1.5 kg chicken thighs","quantity":1.5,"quantityMax":null,"unit":"kg","ingredientId":101,"name":"chicken thigh","note":null,"optional":false,"group":null},
            {"line":"Salt to taste","quantity":null,"quantityMax":null,"unit":null,"ingredientId":105,"name":"salt","note":null,"optional":false,"group":null}],
          "steps":[{"text":"Heat the oven to 180°C.","group":null}],
          "tags":{"flavour":["savoury"],"occasion":[],"source":[]},
          "facts":{"complete":false,"contains":["poultry"],"diets":[]},
          "versions":[{"id":2,"title":"Coq au Vin (slow cooker)","source":"wikibooks","hasImage":false}]}})json";
        recipes->open(1);
        nav->navigateTo("recipe-page");
    }

private slots:
    void initTestCase()
    {
        // Before any Preferences exists, so the owner's real ini is never read or written.
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, dir.path() + "/settings");
    }

    void init()
    {
        engine.reset();
        saved.reset();
        recipes.reset();
        home.reset();
        catalog.reset();
        diet.reset();
        session.reset();
        accounts.reset();
        nav.reset();
        api.reset();
        preferences.reset();
        // A new server for every case, listening before the last one goes, so a late request never reaches it.
        server = std::make_unique<FakeServer>();
        server->responses[path("/device/identify")] = signedIn;
        server->responses[path("/me/diet")] = noDiet;
        server->responses[path("/filters")] = options;
        server->responses[path("/home")] = emptyHome;

        preferences = std::make_unique<Preferences>();
        preferences->resetAll();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server->serverPort()));
        nav = std::make_unique<Nav>();
        accounts = std::make_unique<AccountStore>(dir.path() + "/data");
        session = std::make_unique<Session>(*api);
        diet = std::make_unique<Diet>(*api);
        catalog = std::make_unique<Catalog>(*api, *diet);
        home = std::make_unique<Home>(*api, *diet);
        recipes = std::make_unique<Recipes>(*api);
        saved = std::make_unique<Saved>(*api);
        wireServices(*session, *accounts, *diet, *catalog, *home, *recipes, *saved);
        server->responses[path("/lists")] = R"({"status":"ok","data":[{"id":3,"title":"Cravings","kind":"cravings","count":0}]})";

        // Any warning from Gluttony's own QML (a binding error, an unknown property) fails the test.
        QTest::failOnWarning(QRegularExpression(QStringLiteral("qrc:/qt/qml/Gluttony/")));
    }

    void cleanup()
    {
        engine.reset();
    }

    void signingInOpensTheShellAndLoadsWhatASignInLoads()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        QCOMPARE(nav->currentPage(), QStringLiteral("home-page"));
        QTRY_COMPARE(requestsTo("/me/diet").size(), 1);
        QTRY_COMPARE(requestsTo("/filters").size(), 1);
        QTRY_COMPARE(requestsTo("/home").size(), 1);
        QTRY_COMPARE(requestsTo("/lists").size(), 1);
    }

    void aReloadOfTheOpenRecipeKeepsWhatWasChangedMeanwhile()
    {
        // Recipes says "changed" when a reload starts, while the old detail (and its old `mine`) is still held:
        // showing that would wipe the heart made since. Only a loaded answer is shown.
        const QByteArray detail = R"({"status":"ok","data":{"id":1,"kind":"food","title":"Stub",
          "mine":{"craving":false,"lists":[],"devoured":[],"stars":null,"note":null}}})";
        server->responses[path("/recipes/1")] = detail;
        server->responses[path("/lists/items/add")] = R"({"status":"ok","data":{"listId":3,"recipeId":1,"count":1}})";
        saved->load();
        QTRY_VERIFY(saved->listsLoaded());
        recipes->open(1);
        QTRY_COMPARE(saved->mineId(), 1);
        saved->setCraving(1, true);
        QTRY_VERIFY(saved->mine().value("craving").toBool());

        server->holdNext[path("/recipes/1")] = 1;
        recipes->reload();
        QVERIFY(recipes->loading());
        QCOMPARE(saved->mineId(), 1);
        QVERIFY(saved->mine().value("craving").toBool());

        // The answer is the newest word, so it is shown once it is in. Parked only once the request has arrived.
        QTRY_COMPARE(requestsTo("/recipes/1").size(), 2);
        server->releaseHeld();
        QTRY_VERIFY(!recipes->loading());
        QVERIFY(!saved->mine().value("craving").toBool());
    }

    void openingAnotherRecipeLeavesNoMineOfTheLastOne()
    {
        server->responses[path("/recipes/1")] = R"({"status":"ok","data":{"id":1,"kind":"food","title":"Stub",
          "mine":{"craving":true,"lists":[],"devoured":[],"stars":null,"note":null}}})";
        recipes->open(1);
        QTRY_COMPARE(saved->mineId(), 1);
        server->holdNext[path("/recipes/2")] = 1;
        recipes->open(2);
        QCOMPARE(saved->mineId(), 0);
        QVERIFY(saved->mine().isEmpty());
        QTRY_COMPARE(requestsTo("/recipes/2").size(), 1);
        server->releaseHeld();
    }

    void aNewDeviceSeesTheFormAndCanAskForAKey()
    {
        server->responses[path("/device/identify")] = R"({"status":"new"})";
        start();
        QTRY_VERIFY(findVisible("usernameField"));
        QVERIFY(!findVisible("keyField"));
        click(findVisible("keyBox"));
        QTRY_VERIFY(findVisible("keyField"));
    }

    void aRefusedSignInSaysWhy()
    {
        server->responses[path("/device/identify")] = R"({"status":"new"})";
        server->responses[path("/auth")] = R"({"status":"invalid_credentials","message":"invalid_credentials"})";
        server->statuses[path("/auth")] = 401;
        start();
        QTRY_VERIFY(findVisible("usernameField"));
        session->login("stub", "wrong", QString());
        QTRY_VERIFY(findVisible("loginError"));
    }

    void signingOutGoesBackToTheForm()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        session->logout();
        QTRY_VERIFY(findVisible("loginPage"));
        QVERIFY(catalog->filters() == Catalog::defaultFilters());
    }

    void aPictureThatFailsShowsThePlaceholder()
    {
        // The forced 404 makes QML's Image say so ("QML QQuickImage: Error transferring …"); that is the case under
        // test, not a fault in Gluttony's QML.
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("Image: Error transferring"));
        server->responses[path("/thumbs/1")] = R"({"status":"error","message":"no picture"})";
        server->statuses[path("/thumbs/1")] = 404;
        start();
        QTRY_VERIFY(find("navShell"));
        QQmlComponent component(engine.get());
        component.loadFromModule("Gluttony", "RecipeTile");
        QVERIFY2(component.isReady(), qPrintable(component.errorString()));
        std::unique_ptr<QObject> made(component.createWithInitialProperties(
            {{"recipe", QVariantMap{{"id", 1}, {"title", "Stub"}, {"hasImage", true}, {"kind", "food"}}}}));
        auto *tile = qobject_cast<QQuickItem *>(made.get());
        QVERIFY(tile);
        tile->setParentItem(window()->contentItem());
        QQuickItem *placeholder = findIn(tile, "placeholder");
        QVERIFY(placeholder);
        QTRY_VERIFY(placeholder->isVisible());
        QTRY_COMPARE(requestsTo("/thumbs/1").size(), 1);
    }

    void homeShowsTheTemptationTheMoodsAndThePicks()
    {
        server->responses[path("/home")] = R"({"status":"ok","data":{"date":"2026-10-27",
          "pick":{"id":1,"kind":"food","title":"Stub Coq au Vin","cuisine":"French","totalMinutes":105,"timeFrom":"rule","difficulty":2,"hasImage":false},
          "picks":[{"id":4,"kind":"food","title":"Stub Spinach Eggs","hasImage":false}]}})";
        start();
        QTRY_VERIFY(findVisible("homePickTitle"));
        QCOMPARE(findVisible("homePickTitle")->property("text").toString(), QStringLiteral("Stub Coq au Vin"));
        QVERIFY(findVisible("mood-quick") && findVisible("mood-drinks") && findVisible("goOnThen"));
        QVERIFY(!findVisible("nothingFits"));
    }

    void todaysPicksShowOnlyWholeTiles()
    {
        QJsonArray picks;
        for (int i = 0; i < 8; ++i)
            picks.append(QJsonObject{{"id", 10 + i}, {"kind", "food"}, {"title", "Stub pick"}, {"hasImage", false}});
        const QJsonObject data{{"date", "2026-10-27"}, {"pick", QJsonValue()}, {"picks", picks}};
        server->responses[path("/home")] = QJsonDocument(QJsonObject{{"status", "ok"}, {"data", data}}).toJson();
        start();
        // The widest grab and the narrowest window the app allows.
        for (const int width : {1600, 1100}) {
            window()->resize(width, 1000);
            QTRY_VERIFY(findVisible("tileRowList"));
            QQuickItem *list = findVisible("tileRowList");
            QTRY_COMPARE(list->width(), findVisible("homePage")->width() - 2 * preferences->spacingLarge);
            const int perView = list->property("perView").toInt();
            const qreal tile = list->property("tileWidth").toReal();
            const qreal spacing = list->property("spacing").toReal();
            QVERIFY(tile >= preferences->tileWidth);
            QVERIFY(qAbs(perView * tile + (perView - 1) * spacing - list->width()) < 0.5);
            QVERIFY(perView < picks.size());
        }
    }

    void aMoodOpensBrowseWithItsFilters()
    {
        start();
        QTRY_VERIFY(findVisible("mood-quick"));
        click(findVisible("mood-quick"));
        QTRY_COMPARE(catalog->title(), QStringLiteral("Quick fix"));
        QCOMPARE(catalog->filters().value("maxMinutes").toInt(), 30);
        QCOMPARE(nav->currentPage(), QStringLiteral("results-page"));
    }

    void nothingFitsOffersToSwitchTheDietOff()
    {
        server->responses[path("/me/diet")] = R"({"status":"ok","data":{"diets":["vegan"],"avoid":["gluten","soy"]}})";
        start();
        QTRY_VERIFY(findVisible("nothingFits"));
        QTRY_VERIFY(findVisible("dietOffButton"));
        click(findVisible("dietOffButton"));
        QTRY_VERIFY(!diet->enabled());
        QTRY_COMPARE(QUrlQuery(requestsTo("/home").last()).queryItemValue("profile"), QStringLiteral("off"));
    }

    void anOutageNeverOffersToSwitchTheDietOff()
    {
        server->responses[path("/me/diet")] = R"({"status":"ok","data":{"diets":["vegan"],"avoid":["gluten","soy"]}})";
        server->responses[path("/home")] = R"({"status":"error","message":"server_error"})";
        server->statuses[path("/home")] = 500;
        start();
        QTRY_VERIFY(findVisible("homeError"));
        QVERIFY(!findVisible("nothingFits"));
        QVERIFY(!findVisible("dietOffButton"));
    }

    void aFailedReloadAfterADietChangeShowsNoStalePick()
    {
        server->responses[path("/me/diet")] = R"({"status":"ok","data":{"diets":["vegetarian"],"avoid":[]}})";
        server->responses[path("/home")] = R"({"status":"ok","data":{"date":"2026-10-27",
          "pick":{"id":1,"kind":"food","title":"Stub Coq au Vin","hasImage":false},
          "picks":[{"id":4,"kind":"food","title":"Stub Spinach Eggs","hasImage":false}]}})";
        start();
        QTRY_VERIFY(findVisible("homePickTitle"));
        QTRY_VERIFY(diet->loaded());
        server->responses[path("/home")] = R"({"status":"error","message":"server_error"})";
        server->statuses[path("/home")] = 500;
        click(findVisible("dietEdit"));
        QTRY_VERIFY(findVisible("dietPopup"));
        click(findVisible("avoid-peanut"));
        click(findVisible("dietSave"));
        QTRY_VERIFY(findVisible("homeError"));
        QVERIFY(!findVisible("homePickTitle"));
        QVERIFY(!findVisible("nothingFits"));
    }

    void goOnThenOpensTheRecipe()
    {
        server->responses[path("/random")] = R"({"status":"ok","data":{"recipe":{"id":3,"title":"Stub Mojito"}}})";
        start();
        QTRY_VERIFY(findVisible("goOnThen"));
        click(findVisible("goOnThen"));
        QTRY_COMPARE(recipes->recipeId(), 3);
        QCOMPARE(nav->currentPage(), QStringLiteral("recipe-page"));
    }

    void theDietEditorSavesTheProfile()
    {
        server->responses[path("/me/diet")] = R"({"status":"ok","data":{"diets":["vegetarian"],"avoid":[]}})";
        start();
        QTRY_VERIFY(findVisible("dietChip"));
        click(findVisible("dietEdit"));
        QTRY_VERIFY(findVisible("dietPopup"));
        click(findVisible("avoid-peanut"));
        click(findVisible("dietSave"));
        QTRY_VERIFY(!lastBodyTo("/me/diet").isEmpty());
        const QJsonObject sent = lastBodyTo("/me/diet");
        QCOMPARE(sent.value("diets").toArray().first().toString(), QStringLiteral("vegetarian"));
        QCOMPARE(sent.value("avoid").toArray().first().toString(), QStringLiteral("peanut"));
    }

    void aDietThatFailedToLoadCannotBeOverwritten()
    {
        server->responses[path("/me/diet")] = R"({"status":"error","message":"server_error"})";
        server->statuses[path("/me/diet")] = 500;
        start();
        QTRY_VERIFY(find("navShell"));
        QTRY_VERIFY(!diet->error().isEmpty());
        click(findVisible("dietEdit"));
        QTRY_VERIFY(findVisible("dietPopup"));
        // Opening the editor asks again, and until the profile is in, Save cannot replace it.
        QTRY_COMPARE(requestsTo("/me/diet").size(), 2);
        QVERIFY(!findVisible("dietSave")->isEnabled());
        QTRY_VERIFY(findVisible("dietLoadFailed"));
        // Once the server answers, the saved profile fills the editor and Save comes back.
        server->statuses.remove(path("/me/diet"));
        server->responses[path("/me/diet")] = R"({"status":"ok","data":{"diets":["vegetarian"],"avoid":["peanut"]}})";
        click(findVisible("dietLoadRetry"));
        QTRY_VERIFY(findVisible("dietSave")->isEnabled());
        QVERIFY(!findVisible("dietLoadFailed"));
        QTRY_VERIFY(findVisible("diet-vegetarian")->property("selected").toBool());
        QVERIFY(findVisible("avoid-peanut")->property("selected").toBool());
    }

    void clickingTheDietChipSwitchesItOffForNow()
    {
        server->responses[path("/me/diet")] = R"({"status":"ok","data":{"diets":["vegetarian"],"avoid":["peanut"]}})";
        start();
        QTRY_VERIFY(findVisible("dietChip"));
        click(findVisible("dietChip"));
        QTRY_VERIFY(!diet->enabled());
    }

    void browseShowsTheTilesAndTheCount()
    {
        server->responses[path("/recipes")] = R"({"status":"ok","data":{"total":2,"page":1,"pageSize":24,"recipes":[
          {"id":1,"kind":"food","title":"Stub Coq au Vin","hasImage":false},
          {"id":4,"kind":"food","title":"Stub Spinach Eggs","hasImage":false}]}})";
        start();
        QTRY_VERIFY(find("navShell"));
        catalog->openWith({{"kind", "food"}}, "Quick fix");
        nav->navigateTo("results-page");
        QTRY_VERIFY(findVisible("resultsCount"));
        QCOMPARE(findVisible("resultsTitle")->property("text").toString(), QStringLiteral("Quick fix"));
        QTRY_COMPARE(findVisible("resultsCount")->property("text").toString(), QStringLiteral("2 recipes"));
        QTRY_COMPARE(findVisible("resultsGrid")->property("count").toInt(), 2);
    }

    void tickingAFilterAsksAgainAtOnce()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        catalog->openWith({}, "");
        nav->navigateTo("results-page");
        QTRY_VERIFY(findVisible("filter-effort-1"));
        // The page's own request must have reached the server before it is counted.
        QTRY_COMPARE(requestsTo("/recipes").size(), 1);
        const int before = requestsTo("/recipes").size();
        click(findVisible("filter-effort-1"));
        QTRY_COMPARE(requestsTo("/recipes").size(), before + 1);
        QCOMPARE(QUrlQuery(requestsTo("/recipes").last()).queryItemValue("difficulty"), QStringLiteral("1"));
        QTRY_VERIFY(findVisible("filter-effort-1")->property("selected").toBool());
    }

    void emptyResultsSayNothingFitsAndOfferTheDietOff()
    {
        server->responses[path("/me/diet")] = R"({"status":"ok","data":{"diets":["vegan"],"avoid":[]}})";
        server->responses[path("/recipes")] = R"({"status":"ok","data":{"total":0,"page":1,"pageSize":24,"recipes":[]}})";
        start();
        QTRY_VERIFY(diet->loaded());
        catalog->openWith({{"kind", "drink"}}, "Bottoms up");
        nav->navigateTo("results-page");
        QTRY_VERIFY(findVisible("resultsEmpty"));
        click(findVisible("resultsDietOff"));
        QTRY_COMPARE(QUrlQuery(requestsTo("/recipes").last()).queryItemValue("profile"), QStringLiteral("off"));
    }

    void thePanelCollapsesToAButtonAndComesBack()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        nav->navigateTo("results-page");
        QTRY_VERIFY(findVisible("hideFilters"));
        // A click only reaches the chips once the panel has laid itself out (its scrolling content has a height).
        QTRY_VERIFY(find("filterPanel")->childItems().value(0)->property("contentHeight").toDouble() > 0);
        click(findVisible("hideFilters"));
        QTRY_VERIFY(!findVisible("filterPanel"));
        QVERIFY(preferences->filterPanelCollapsed);
        // Nothing is ticked, so the button carries no count.
        QCOMPARE(findVisible("showFilters")->property("text").toString(), QStringLiteral("Filters"));
        click(findVisible("showFilters"));
        QTRY_VERIFY(findVisible("filterPanel"));
    }

    void resultsShowTheDietChipWithThePanelCollapsed()
    {
        server->responses[path("/me/diet")] = R"({"status":"ok","data":{"diets":["vegetarian"],"avoid":["peanut"]}})";
        preferences->filterPanelCollapsed = true;
        start();
        QTRY_VERIFY(diet->loaded());
        catalog->openWith({}, "");
        nav->navigateTo("results-page");
        QTRY_VERIFY(findVisible("showFilters"));
        QVERIFY(!findVisible("filterPanel"));
        QTRY_VERIFY(findVisible("resultsPage"));
        QVERIFY(findIn(findVisible("resultsPage"), "dietChip", true));
    }

    void anIngredientPickedBecomesMustInclude()
    {
        server->responses[path("/ingredients")] = R"({"status":"ok","data":[{"id":301,"name":"egg"}]})";
        start();
        QTRY_VERIFY(find("navShell"));
        nav->navigateTo("results-page");
        QTRY_VERIFY(findVisible("picker-include"));
        findVisible("picker-include")->forceActiveFocus();
        // QTest has no keyClicks for a window, so the letters go one by one.
        QTest::keyClick(window(), Qt::Key_E);
        QTest::keyClick(window(), Qt::Key_G);
        QTRY_VERIFY(findVisible("match-include-0"));
        click(findVisible("match-include-0"));
        QTRY_COMPARE(catalog->filters().value("include").toList().size(), 1);
        QTRY_COMPARE(QUrlQuery(requestsTo("/recipes").last()).queryItemValue("include"), QStringLiteral("301"));
    }

    void typingShowsRecipesAndIngredients()
    {
        server->responses[path("/recipes")] = R"({"status":"ok","data":{"total":1,"page":1,"pageSize":6,"recipes":[
          {"id":4,"kind":"food","title":"Stub Spinach Eggs","hasImage":false}]}})";
        server->responses[path("/ingredients")] = R"({"status":"ok","data":[{"id":301,"name":"egg"}]})";
        start();
        QTRY_VERIFY(find("navShell"));
        click(findVisible("searchField"));
        type("eg");
        QTRY_VERIFY(findVisible("quickRecipe-0"));
        QTRY_VERIFY(findVisible("quickIngredient-0"));
    }

    void enterWithNothingHighlightedSearchesEverything()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        click(findVisible("searchField"));
        type("coq au vin");
        QTest::keyClick(window(), Qt::Key_Return);
        QTRY_COMPARE(catalog->title(), QStringLiteral("coq au vin"));
        QCOMPARE(nav->currentPage(), QStringLiteral("results-page"));
        QCOMPARE(findVisible("searchField")->property("text").toString(), QString());
    }

    void aLongLineIsSearchedAsItsFirstHundredCharacters()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        click(findVisible("searchField"));
        type(QString(120, QLatin1Char('a')));
        QTest::keyClick(window(), Qt::Key_Return);
        QTRY_COMPARE(nav->currentPage(), QStringLiteral("results-page"));
        // The quick look-up also asks /recipes (six at a time), so the page's own request is the one that is not.
        // requestsTo returns a new list each call, so the scan takes one copy.
        const auto pageAsked = [this] {
            const QList<QUrl> asked = requestsTo("/recipes");
            return std::any_of(asked.cbegin(), asked.cend(), [](const QUrl &url) {
                return QUrlQuery(url).queryItemValue("pageSize") != QLatin1String("6");
            });
        };
        QTRY_VERIFY(pageAsked());
        const QList<QUrl> asked = requestsTo("/recipes");
        for (const QUrl &url : asked)
            QVERIFY(QUrlQuery(url).queryItemValue("q").size() <= 100);
    }

    void theArrowsWalkToAnIngredientAndEnterIncludesIt()
    {
        server->responses[path("/recipes")] = R"({"status":"ok","data":{"total":1,"page":1,"pageSize":6,"recipes":[
          {"id":4,"kind":"food","title":"Stub Spinach Eggs","hasImage":false}]}})";
        server->responses[path("/ingredients")] = R"({"status":"ok","data":[{"id":301,"name":"egg"}]})";
        start();
        QTRY_VERIFY(find("navShell"));
        click(findVisible("searchField"));
        type("eg");
        QTRY_VERIFY(findVisible("quickIngredient-0"));
        QTest::keyClick(window(), Qt::Key_Down);
        QTest::keyClick(window(), Qt::Key_Down);
        QTest::keyClick(window(), Qt::Key_Return);
        QTRY_COMPARE(catalog->filters().value("include").toList().size(), 1);
        QCOMPARE(nav->currentPage(), QStringLiteral("results-page"));
    }

    void ctrlKPutsTheCursorInTheSearch()
    {
        start();
        QTRY_VERIFY(findVisible("searchField"));
        QTest::keyClick(window(), Qt::Key_K, Qt::ControlModifier);
        QTRY_VERIFY(findVisible("searchField")->hasActiveFocus());
    }

    void theRecipePageShowsItsLinesAndSteps()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        openRecipeOne();
        QTRY_VERIFY(findVisible("recipeTitle"));
        QCOMPARE(findVisible("recipeTitle")->property("text").toString(), QStringLiteral("Stub Coq au Vin"));
        QCOMPARE(findVisible("ingredient-0")->property("text").toString(), QStringLiteral("1.5 kg chicken thighs"));
        QCOMPARE(findVisible("ingredient-1")->property("text").toString(), QStringLiteral("Salt to taste"));
        QCOMPARE(findVisible("step-0")->property("text").toString(), QStringLiteral("Heat the oven to 180°C (355°F)."));
    }

    void moreServingsAndUsUnitsChangeTheLines()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        openRecipeOne();
        QTRY_VERIFY(findVisible("servingsPlus"));
        click(findVisible("servingsPlus"));
        QTRY_COMPARE(findVisible("ingredient-0")->property("text").toString(), QStringLiteral("1.88 kg chicken thighs"));
        click(findVisible("units-us"));
        QTRY_COMPARE(findVisible("ingredient-0")->property("text").toString(), QStringLiteral("4⅛ lb chicken thighs"));
        QCOMPARE(preferences->units, QStringLiteral("us"));
    }

    void secondsShowsTheOtherVersion()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        openRecipeOne();
        QTRY_VERIFY(findVisible("recipeTitle"));
        bool found = false;
        QList<QQuickItem *> pending{window()->contentItem()};
        while (!pending.isEmpty() && !found) {
            QQuickItem *item = pending.takeFirst();
            found = item->objectName() == "tileTitle" && item->property("text").toString() == "Coq au Vin (slow cooker)";
            pending += item->childItems();
        }
        QVERIFY(found);
    }

    void anIncompleteRecipeWarnsWhileTheDietIsOn()
    {
        server->responses[path("/me/diet")] = R"({"status":"ok","data":{"diets":["vegetarian"],"avoid":[]}})";
        start();
        QTRY_VERIFY(diet->loaded());
        openRecipeOne();
        QTRY_VERIFY(findVisible("unknownWarning"));
        diet->setEnabled(false);
        QTRY_VERIFY(!findVisible("unknownWarning"));
    }

    void theRecipePageSaysWhenARecipeHasGone()
    {
        server->responses[path("/recipes/999")] = R"({"status":"error","message":"no such recipe"})";
        server->statuses[path("/recipes/999")] = 404;
        start();
        QTRY_VERIFY(find("navShell"));
        nav->navigateTo("home-page");
        recipes->open(999);
        nav->navigateTo("recipe-page");
        QTRY_VERIFY(findVisible("recipeGone"));
        click(findVisible("recipeGoneBack"));
        QTRY_COMPARE(nav->currentPage(), QStringLiteral("home-page"));
    }

    void aReloadThatFindsTheRecipeGoneShowsNoStaleContent()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        openRecipeOne();
        QTRY_VERIFY(findVisible("recipeTitle"));
        // Recipes keeps the old recipe map on a 404, so the page itself must put the gone state first.
        server->responses[path("/recipes/1")] = R"({"status":"error","message":"no such recipe"})";
        server->statuses[path("/recipes/1")] = 404;
        recipes->reload();
        QTRY_VERIFY(findVisible("recipeGone"));
        QVERIFY(!findVisible("recipeTitle"));
        QVERIFY(!findVisible("ingredient-0"));
    }

    void aLongIngredientsColumnScrollsWithThePage()
    {
        QJsonArray lines;
        for (int i = 0; i < 40; ++i)
            lines.append(QJsonObject{{"line", QStringLiteral("Stub ingredient %1").arg(i + 1)}, {"quantity", QJsonValue()},
                                     {"quantityMax", QJsonValue()}, {"unit", QJsonValue()}, {"ingredientId", QJsonValue()},
                                     {"name", QJsonValue()}, {"note", QJsonValue()}, {"optional", false},
                                     {"group", QJsonValue()}});
        // Three long steps, so the method runs on past the ingredients and the column would stay pinned.
        QJsonArray steps;
        for (int i = 0; i < 3; ++i)
            steps.append(QJsonObject{{"text", QString("Stir the pot slowly and keep it warm. ").repeated(90)},
                                     {"group", QJsonValue()}});
        const QJsonObject recipe{{"id", 5}, {"kind", "food"}, {"title", "Stub Long Stew"}, {"course", "main"},
                                 {"cuisine", "French"}, {"servings", 4}, {"servingsFrom", "source"},
                                 {"totalMinutes", 105}, {"timeFrom", "rule"}, {"difficulty", 2},
                                 {"difficultyFrom", "rule"}, {"hasImage", false}, {"source", "wikibooks"},
                                 {"sourceUrl", QJsonValue()}, {"licence", "CC BY-SA 4.0"},
                                 {"credit", "Stub Long Stew"}, {"imageCredit", QJsonValue()},
                                 {"videoUrl", QJsonValue()}, {"ingredients", lines},
                                 {"steps", steps}, {"facts", QJsonObject{{"complete", true}, {"contains", QJsonArray()},
                                                                         {"diets", QJsonArray()}}},
                                 {"tags", QJsonObject{{"flavour", QJsonArray()}}}, {"versions", QJsonArray()}};
        server->responses[path("/recipes/5")] = QJsonDocument(QJsonObject{{"status", "ok"}, {"data", recipe}}).toJson();
        start();
        QTRY_VERIFY(find("navShell"));
        // Shorter than the forty lines, so they cannot all be in view at once.
        window()->resize(1600, 900);
        recipes->open(5);
        nav->navigateTo("recipe-page");
        QTRY_VERIFY(findVisible("ingredient-39"));
        QQuickItem *column = findVisible("ingredientsColumn");
        QVERIFY(column);
        QQuickItem *body = column->parentItem();
        // The column sits in body, in page, in the Flickable's content item.
        QQuickItem *flick = body->parentItem()->parentItem()->parentItem();
        QVERIFY(flick && flick->inherits("QQuickFlickable"));
        QTRY_VERIFY(column->implicitHeight() > flick->height());
        QTRY_VERIFY(body->height() > column->implicitHeight());
        // Scrolled to where the column's last line meets the bottom of the view, as a cook reading step one would.
        const qreal target = body->y() + column->implicitHeight() - flick->height() + 24;
        flick->setProperty("contentY", target);
        QQuickItem *last = findVisible("ingredient-39");
        QTRY_VERIFY(last->mapToItem(flick, QPointF(0, last->height())).y() <= flick->height());
        QVERIFY(last->mapToItem(flick, QPointF(0, 0)).y() >= 0);
    }

    void aGuessedEffortReadsAbout()
    {
        start();
        QTRY_VERIFY(find("navShell"));
        openRecipeOne();
        QTRY_VERIFY(findVisible("recipeTitle"));
        bool found = false;
        QList<QQuickItem *> pending{window()->contentItem()};
        while (!pending.isEmpty() && !found) {
            QQuickItem *item = pending.takeFirst();
            found = item->isVisible() && item->property("text").toString() == QLatin1String("about medium");
            pending += item->childItems();
        }
        QVERIFY(found);
    }
};

QTEST_MAIN(TestPages)
#include "tst_pages.moc"
