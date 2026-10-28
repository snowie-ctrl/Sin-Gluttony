#include <QCoreApplication>
#include <QDesktopServices>
#include <QGuiApplication>
#include <QIcon>
#include <QMouseEvent>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QSettings>
#include <QStandardPaths>
#include <QTimer>
#include <QUrlQuery>
#include <QtQml/QQmlExtensionPlugin>

#include "LinkSuppressor.h"
#include "api/Api.h"
#include "api/AuthNetworkFactory.h"
#include "assets/Preferences.h"
#include "services/AccountStore.h"
#include "services/Catalog.h"
#include "services/Diet.h"
#include "services/Home.h"
#include "services/Nav.h"
#include "services/Recipes.h"
#include "services/Session.h"
#include "services/Wiring.h"

// The QML module is a static library (gluttony_ui), so its plugin is pulled in by hand.
Q_IMPORT_QML_PLUGIN(GluttonyPlugin)

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    QCoreApplication::setApplicationName(QStringLiteral("Gluttony"));
    app.setWindowIcon(QIcon(QStringLiteral(":/images/gluttony.svg")));

    // Screenshot runs (tests/stub/grab.ps1) keep their own preferences and account folders, so trying a page never
    // changes the owner's.
    const QString settingsDir = qEnvironmentVariable("GLUTTONY_SETTINGS_DIR");
    if (!settingsDir.isEmpty())
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, settingsDir);
    QString dataDir = qEnvironmentVariable("GLUTTONY_DATA_DIR");
    if (dataDir.isEmpty())
        dataDir = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);

    Preferences preferences;
    Api api;
    Nav nav;
    AccountStore accountStore(dataDir);
    Session session(api);
    Diet diet(api);
    Catalog catalog(api, diet);
    Home home(api, diet);
    Recipes recipes(api);
    // Pictures load as plain Images through managers this makes, so they carry the session token.
    AuthNetworkFactory networkFactory;

    wireServices(session, accountStore, diet, catalog, home, recipes);

    // Declared after everything QML is given, so it is destroyed first.
    QQmlApplicationEngine engine;
    engine.setNetworkAccessManagerFactory(&networkFactory);
    QQmlContext *context = engine.rootContext();
    context->setContextProperty("Preferences", &preferences);
    context->setContextProperty("Nav", &nav);
    context->setContextProperty("Session", &session);
    context->setContextProperty("Diet", &diet);
    context->setContextProperty("Catalog", &catalog);
    context->setContextProperty("Home", &home);
    context->setContextProperty("Recipes", &recipes);

    engine.loadFromModule("Gluttony", "Main");
    if (engine.rootObjects().isEmpty())
        return -1;

    // Dev affordances for grab.ps1: open on a page, a recipe or a search once signed in, in a chosen time zone.
    // Nothing happens unless the variables are set.
    const QString startPage = qEnvironmentVariable("GLUTTONY_START_PAGE");
    if (!startPage.isEmpty())
        nav.setStartPage(startPage);
    const int startRecipe = qEnvironmentVariableIntValue("GLUTTONY_START_RECIPE");
    if (startRecipe > 0) {
        nav.setStartPage(QStringLiteral("recipe-page"));
        QObject::connect(&session, &Session::loginSucceeded, &recipes,
                         [&recipes, startRecipe]() { recipes.open(startRecipe); }, Qt::SingleShotConnection);
    }
    const QString startQuery = qEnvironmentVariable("GLUTTONY_START_QUERY");
    if (!startQuery.isEmpty()) {
        nav.setStartPage(QStringLiteral("results-page"));
        QVariantMap preset;
        for (const auto &item : QUrlQuery(startQuery).queryItems(QUrl::FullyDecoded))
            preset.insert(item.first, item.second);
        QObject::connect(&session, &Session::loginSucceeded, &catalog, [&catalog, preset]() {
            catalog.openWith(preset, preset.value("title").toString());
        }, Qt::SingleShotConnection);
    }
    const QString timeZone = qEnvironmentVariable("GLUTTONY_TZ");
    if (!timeZone.isEmpty())
        home.setTimeZone(timeZone);

    // A known device signs itself in; otherwise the sign-in page asks.
    session.identifyDevice();

    // A grab or a scripted click must never open the owner's browser (a recipe's source link): such a link is
    // swallowed and logged. A normal run installs nothing.
    LinkSuppressor linkSuppressor;
    if (!qEnvironmentVariable("GLUTTONY_GRAB").isEmpty() || !qEnvironmentVariable("GLUTTONY_CLICK").isEmpty()) {
        QDesktopServices::setUrlHandler(QStringLiteral("https"), &linkSuppressor, "suppress");
        QDesktopServices::setUrlHandler(QStringLiteral("http"), &linkSuppressor, "suppress");
    }

    // Dev affordance for layout checks: left clicks at "x,y" (window
    // coordinates), several separated by ';', 1.5 s apart after a first delay,
    // to open something before GLUTTONY_GRAB takes its picture. Does nothing
    // unless the variable is set.
    const QStringList clicks = qEnvironmentVariable("GLUTTONY_CLICK").split(';', Qt::SkipEmptyParts);
    const int clickDelay = qEnvironmentVariableIntValue("GLUTTONY_CLICK_DELAY");
    for (int i = 0; i < clicks.size(); ++i) {
        const QStringList clickAt = clicks[i].split(',');
        if (clickAt.size() != 2)
            continue;
        const QPointF point(clickAt[0].toDouble(), clickAt[1].toDouble());
        QTimer::singleShot((clickDelay > 0 ? clickDelay : 5000) + i * 1500, &app, [&engine, point]() {
            auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().value(0));
            if (!window)
                return;
            QMouseEvent press(QEvent::MouseButtonPress, point, window->mapToGlobal(point),
                              Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
            QMouseEvent release(QEvent::MouseButtonRelease, point, window->mapToGlobal(point),
                                Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
            QCoreApplication::sendEvent(window, &press);
            QCoreApplication::sendEvent(window, &release);
        });
    }

    // Dev affordance for layout checks: save the window to a PNG after a
    // delay, then quit. Does nothing unless the variable is set.
    const QString grabPath = qEnvironmentVariable("GLUTTONY_GRAB");
    if (!grabPath.isEmpty()) {
        // The window opens on the owner's desktop, and a real click or key
        // landing on it would change what is grabbed (and report progress).
        // GLUTTONY_CLICK sends its events straight to the window, so it
        // still works.
        // Changing the flags of a window already shown makes Windows lay its
        // frame out again, which grows the window; the size is put back so
        // grabs stay the size Main.qml asks for.
        // GLUTTONY_GRAB_SIZE ("2560x1440") grabs at a real screen's size, to
        // judge how pages look where they will be read.
        if (auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().value(0))) {
            QSize size = window->size();
            const QStringList asked = qEnvironmentVariable("GLUTTONY_GRAB_SIZE").split('x');
            if (asked.size() == 2 && asked[0].toInt() > 0 && asked[1].toInt() > 0)
                size = QSize(asked[0].toInt(), asked[1].toInt());
            window->setFlags(window->flags() | Qt::WindowTransparentForInput | Qt::WindowDoesNotAcceptFocus);
            window->resize(size);
        }
        const int grabDelay = qEnvironmentVariableIntValue("GLUTTONY_GRAB_DELAY");
        QTimer::singleShot(grabDelay > 0 ? grabDelay : 6000, &app, [&engine, grabPath]() {
            if (auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().value(0)))
                window->grabWindow().save(grabPath);
            QCoreApplication::quit();
        });
    }

    return app.exec();
}
