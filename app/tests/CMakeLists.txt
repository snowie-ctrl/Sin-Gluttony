find_package(Qt6 REQUIRED COMPONENTS Test Gui Network Qml Quick)

# One test executable: its sources, the libraries beyond Qt Test, and a ctest entry. Console programs, so their
# output reaches ctest; offscreen, so no window reaches the owner's screen.
function(gluttony_test name)
    cmake_parse_arguments(T "" "" "SOURCES;LIBS" ${ARGN})
    qt_add_executable(${name} ${T_SOURCES})
    target_include_directories(${name} PRIVATE ..)
    target_link_libraries(${name} PRIVATE Qt6::Test ${T_LIBS})
    set_target_properties(${name} PROPERTIES WIN32_EXECUTABLE FALSE MACOSX_BUNDLE FALSE)
    add_test(NAME ${name} COMMAND ${name})
    set_tests_properties(${name} PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endfunction()

gluttony_test(tst_api
    SOURCES tst_api.cpp FakeServer.h
            ../api/Api.h ../api/Api.cpp ../api/AppConfig.h
            ../api/SessionAuth.h ../api/SessionAuth.cpp
    LIBS Qt6::Network)

gluttony_test(tst_sessionauth
    SOURCES tst_sessionauth.cpp FakeServer.h
            ../api/SessionAuth.h ../api/SessionAuth.cpp ../api/AuthNetworkFactory.h
    LIBS Qt6::Network Qt6::Qml)

gluttony_test(tst_preferences
    SOURCES tst_preferences.cpp ../assets/Preferences.h ../assets/Preferences.cpp
    LIBS Qt6::Gui)

gluttony_test(tst_accountstore
    SOURCES tst_accountstore.cpp ../services/AccountStore.h ../services/AccountStore.cpp)

gluttony_test(tst_session
    SOURCES tst_session.cpp FakeServer.h
            ../api/Api.h ../api/Api.cpp ../api/AppConfig.h
            ../api/SessionAuth.h ../api/SessionAuth.cpp
            ../services/AccountStore.h ../services/AccountStore.cpp
            ../services/Session.h ../services/Session.cpp
    LIBS Qt6::Network)

gluttony_test(tst_diet
    SOURCES tst_diet.cpp FakeServer.h
            ../api/Api.h ../api/Api.cpp ../api/AppConfig.h ../api/SessionAuth.h ../api/SessionAuth.cpp
            ../services/Diet.h ../services/Diet.cpp
    LIBS Qt6::Network)

gluttony_test(tst_recipequery
    SOURCES tst_recipequery.cpp FakeServer.h
            ../api/Api.h ../api/Api.cpp ../api/AppConfig.h ../api/SessionAuth.h ../api/SessionAuth.cpp ../api/TileModel.h
            ../services/RecipeQuery.h ../services/RecipeQuery.cpp
    LIBS Qt6::Network)

gluttony_test(tst_catalog
    SOURCES tst_catalog.cpp FakeServer.h
            ../api/Api.h ../api/Api.cpp ../api/AppConfig.h ../api/SessionAuth.h ../api/SessionAuth.cpp ../api/TileModel.h
            ../services/Diet.h ../services/Diet.cpp
            ../services/RecipeQuery.h ../services/RecipeQuery.cpp
            ../services/Catalog.h ../services/Catalog.cpp
    LIBS Qt6::Network)

gluttony_test(tst_home
    SOURCES tst_home.cpp FakeServer.h
            ../api/Api.h ../api/Api.cpp ../api/AppConfig.h ../api/SessionAuth.h ../api/SessionAuth.cpp
            ../services/Diet.h ../services/Diet.cpp ../services/Home.h ../services/Home.cpp
    LIBS Qt6::Network)

gluttony_test(tst_recipes
    SOURCES tst_recipes.cpp FakeServer.h
            ../api/Api.h ../api/Api.cpp ../api/AppConfig.h ../api/SessionAuth.h ../api/SessionAuth.cpp
            ../services/Recipes.h ../services/Recipes.cpp
    LIBS Qt6::Network)

gluttony_test(tst_pages
    SOURCES tst_pages.cpp FakeServer.h ../assets/resources.qrc
            ../assets/Preferences.h ../assets/Preferences.cpp
            ../api/Api.h ../api/Api.cpp ../api/AppConfig.h ../api/SessionAuth.h ../api/SessionAuth.cpp ../api/TileModel.h
            ../services/Nav.h ../services/AccountStore.h ../services/AccountStore.cpp
            ../services/Session.h ../services/Session.cpp ../services/Diet.h ../services/Diet.cpp
            ../services/RecipeQuery.h ../services/RecipeQuery.cpp ../services/Catalog.h ../services/Catalog.cpp
            ../services/Home.h ../services/Home.cpp ../services/Recipes.h ../services/Recipes.cpp
            ../services/Wiring.h ../services/Wiring.cpp
    LIBS Qt6::Network Qt6::Quick Qt6::QuickControls2 gluttony_uiplugin)
