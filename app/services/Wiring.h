#pragma once

class AccountStore;
class Catalog;
class Cook;
class Diet;
class Home;
class RecipeStore;
class Recipes;
class Saved;
class Session;
class SyncQueue;

// What follows a person in and out: the account folder opens and closes with the session, and the device's copies,
// the offline queue and cook mode's places follow it; a sign-in (or a reconnect after an offline start) loads their
// diet, the filter options, Home and their lists, and an offline start loads the lists from the copies. The recipe
// page's detail tells Saved what the person keeps on it, and every change to that reaches the recipe's copy; opening
// cook mode keeps its recipe on the device. A sign-out leaves nothing of theirs for the next person.
// main.cpp and tests/tst_pages.cpp wire the app with this one function.
void wireServices(Session &session, AccountStore &store, Diet &diet, Catalog &catalog, Home &home, Recipes &recipes,
                  Saved &saved, RecipeStore &copies, SyncQueue &queue, Cook &cook);
