#include "services/Wiring.h"

#include <QTimer>

#include "services/AccountStore.h"
#include "services/Catalog.h"
#include "services/Cook.h"
#include "services/Diet.h"
#include "services/Home.h"
#include "services/RecipeStore.h"
#include "services/Recipes.h"
#include "services/Saved.h"
#include "services/Session.h"
#include "services/SyncQueue.h"


void wireServices(Session &session, AccountStore &store, Diet &diet, Catalog &catalog, Home &home, Recipes &recipes,
                  Saved &saved, RecipeStore &copies, SyncQueue &queue, Cook &cook)
{
    session.setStore(&store);
    // Each follows the account's folder (AccountStore::changed). Session opens the folder before it sets the token,
    // so the copies and the queue have moved to the new account before anything is sent as it.
    copies.setStore(&store);
    queue.setStore(&store);
    cook.setStore(&store);
    recipes.setStore(&copies);
    saved.setStore(&copies);
    saved.setQueue(&queue);
    copies.setWaiting([&queue](int recipeId) { return queue.waits(recipeId); });

    const auto signedIn = [&diet, &catalog, &home, &saved]() {
        diet.load();
        catalog.loadOptions();
        home.load();
        saved.load();
    };
    QObject::connect(&session, &Session::loginSucceeded, &diet, signedIn);
    QObject::connect(&session, &Session::reconnected, &diet, signedIn);
    // Opened offline: the lists are the copies' until the server answers (reconnected then loads them as a sign-in does).
    QObject::connect(&session, &Session::startedOffline, &saved, [&saved]() { saved.load(); });

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
        saved.showMine(recipes.recipeId(), recipe.value("mine").toMap(), recipe.value("title").toString());
    });

    // What the person keeps on the open recipe, changed here or by the queue's answer, reaches its copy, so the
    // recipe shows it with no server too.
    QObject::connect(&saved, &Saved::mineChanged, &copies, [&saved, &copies]() {
        if (saved.mineId() > 0 && !saved.mine().isEmpty())
            copies.patchMine(saved.mineId(), saved.mine());
    });

    // Spec §5: opening cook mode stores the recipe on the device. The recipe is as the page loaded it, so its `mine`
    // is out of date by whatever was kept since (a note queued offline, a star): Saved's is the live one, and the
    // copy must not go back to the old.
    QObject::connect(&cook, &Cook::opened, &copies, [&copies, &saved](const QVariantMap &recipe) {
        QVariantMap kept = recipe;
        if (saved.mineId() == recipe.value("id").toInt() && !saved.mine().isEmpty())
            kept.insert("mine", saved.mine());
        copies.keepForCooking(kept);
    });

    // The copies follow the manifest, which is otherwise asked for only at sign-in and on reconnect: a recipe hearted
    // at lunch must be on the device when the Wi-Fi drops at dinner. A short single-shot wait, restarted by each
    // change, so a run of hearts costs one manifest.
    auto *refreshSoon = new QTimer(&copies);
    refreshSoon->setSingleShot(true);
    refreshSoon->setInterval(2000);
    QObject::connect(refreshSoon, &QTimer::timeout, &copies, &RecipeStore::refresh);
    QObject::connect(&saved, &Saved::listsKept, refreshSoon, qOverload<>(&QTimer::start));
    // What the queue's answer settled reaches every copy, not only the open recipe's: the manifest, which carries
    // each recipe's `mine`, is asked again once the server has taken the changes.
    QObject::connect(&queue, &SyncQueue::taken, refreshSoon, qOverload<>(&QTimer::start));
    // A discarded change was shown on its copy as a star or note the server never took: the manifest is asked again
    // so the copy goes back to what the server keeps.
    QObject::connect(&queue, &SyncQueue::discarded, refreshSoon, qOverload<>(&QTimer::start));

    // A ♥ or a Devoured mark changes Home's own rows (and a mark changes today's temptation): Home asks again
    // on its next visit.
    QObject::connect(&saved, &Saved::keptChanged, &home, &Home::markStale);

    // The catalog and Home are cleared before the diet, whose clearing switches it back on: by then nothing is
    // left to ask again.
    QObject::connect(&session, &Session::signedOut, &diet, [&diet, &catalog, &home, &recipes, &saved, &cook]() {
        // The sign-in page takes the screen, so cook mode closes. Its timers stay: they end with the account (Cook
        // follows the folder), not with a session the server ended mid-roast.
        if (cook.active())
            cook.close();
        catalog.clear();
        home.clear();
        recipes.clear();
        saved.clear();
        diet.clear();
    });
}
