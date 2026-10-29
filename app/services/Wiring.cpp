#include "services/Wiring.h"

#include "services/AccountStore.h"
#include "services/Catalog.h"
#include "services/Diet.h"
#include "services/Home.h"
#include "services/Recipes.h"
#include "services/Saved.h"
#include "services/Session.h"


void wireServices(Session &session, AccountStore &store, Diet &diet, Catalog &catalog, Home &home, Recipes &recipes,
                  Saved &saved)
{
    session.setStore(&store);

    const auto signedIn = [&diet, &catalog, &home, &saved]() {
        diet.load();
        catalog.loadOptions();
        home.load();
        saved.load();
    };
    QObject::connect(&session, &Session::loginSucceeded, &diet, signedIn);
    QObject::connect(&session, &Session::reconnected, &diet, signedIn);

    // The recipe page's actions read what the person keeps on the open recipe; an empty recipe (loading, gone,
    // signed out) keeps nothing. Recipes also says "changed" when a reload starts, while the old detail is still
    // held: its `mine` is out of date by then (a craving made since), so only a loaded answer is shown.
    QObject::connect(&recipes, &Recipes::changed, &saved, [&recipes, &saved]() {
        const QVariantMap recipe = recipes.recipe();
        if (recipes.loading() && !recipe.isEmpty())
            return;
        // A recipe that is gone, or none yet, keeps nothing.
        if (recipes.gone() || recipe.isEmpty()) {
            saved.showMine(0, QVariantMap());
            return;
        }
        // A reload that failed leaves the old detail held: what was changed since is newer than its `mine`.
        if (!recipes.error().isEmpty())
            return;
        saved.showMine(recipes.recipeId(), recipe.value("mine").toMap());
    });

    // The catalog and Home are cleared before the diet, whose clearing switches it back on: by then nothing is
    // left to ask again.
    QObject::connect(&session, &Session::signedOut, &diet, [&diet, &catalog, &home, &recipes, &saved]() {
        catalog.clear();
        home.clear();
        recipes.clear();
        saved.clear();
        diet.clear();
    });
}
