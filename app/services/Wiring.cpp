#include "services/Wiring.h"

#include "services/AccountStore.h"
#include "services/Catalog.h"
#include "services/Diet.h"
#include "services/Home.h"
#include "services/Recipes.h"
#include "services/Session.h"


void wireServices(Session &session, AccountStore &store, Diet &diet, Catalog &catalog, Home &home, Recipes &recipes)
{
    session.setStore(&store);

    const auto signedIn = [&diet, &catalog, &home]() {
        diet.load();
        catalog.loadOptions();
        home.load();
    };
    QObject::connect(&session, &Session::loginSucceeded, &diet, signedIn);
    QObject::connect(&session, &Session::reconnected, &diet, signedIn);

    // The catalog and Home are cleared before the diet, whose clearing switches it back on: by then nothing is
    // left to ask again.
    QObject::connect(&session, &Session::signedOut, &diet, [&diet, &catalog, &home, &recipes]() {
        catalog.clear();
        home.clear();
        recipes.clear();
        diet.clear();
    });
}
