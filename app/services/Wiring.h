#pragma once

class AccountStore;
class Catalog;
class Diet;
class Home;
class Recipes;
class Session;

// What follows a person in and out: the account folder opens and closes with the session, a sign-in (or a
// reconnect after an offline start) loads their diet, the filter options and Home, and a sign-out leaves nothing
// of theirs for the next person. main.cpp and tests/tst_pages.cpp wire the app with this one function.
void wireServices(Session &session, AccountStore &store, Diet &diet, Catalog &catalog, Home &home, Recipes &recipes);
