cmake_minimum_required(VERSION 3.16)

project(Gluttony VERSION 0.1 LANGUAGES CXX)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 REQUIRED COMPONENTS Quick QuickControls2 Network)

qt_standard_project_setup(REQUIRES 6.8)

qt_add_executable(appGluttony
    main.cpp
    LinkSuppressor.h

    assets/resources.qrc
    assets/Preferences.h
    assets/Preferences.cpp

    api/AppConfig.h
    api/Api.h
    api/Api.cpp
    api/SessionAuth.h
    api/SessionAuth.cpp
    api/AuthNetworkFactory.h
    api/TileModel.h

    services/Nav.h
    services/AccountStore.h
    services/AccountStore.cpp
    services/Session.h
    services/Session.cpp
    services/Diet.h
    services/Diet.cpp
    services/RecipeQuery.h
    services/RecipeQuery.cpp
    services/Catalog.h
    services/Catalog.cpp
    services/Home.h
    services/Home.cpp
    services/Recipes.h
    services/Recipes.cpp
    services/Saved.h
    services/Saved.cpp
    services/Wiring.h
    services/Wiring.cpp
)

# The QML lives in a static library of its own, so test harnesses (tests/tst_pages.cpp) load the real pages.
qt_add_library(gluttony_ui STATIC)
qt_add_qml_module(gluttony_ui
    URI Gluttony
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/NavShell.qml
        qml/pages/LoginPage.qml
        qml/pages/HomePage.qml
        qml/pages/ResultsPage.qml
        qml/pages/RecipePage.qml
        qml/pages/SavedPage.qml
        qml/pages/SettingsPage.qml
        qml/component/TintedIcon.qml
        qml/component/ActionButton.qml
        qml/component/InputField.qml
        qml/component/Chip.qml
        qml/component/PictureFrame.qml
        qml/component/RecipeTile.qml
        qml/component/TileRow.qml
        qml/component/DietChip.qml
        qml/component/DietPopup.qml
        qml/component/FilterPanel.qml
        qml/component/SearchBar.qml
        qml/component/Stars.qml
        qml/component/ListPopup.qml
        qml/component/NotePopup.qml
        qml/component/TitlePopup.qml
        qml/logic/scale.mjs
        qml/logic/units.mjs
        qml/logic/words.mjs
        qml/logic/moods.mjs
        qml/logic/tiles.mjs
        qml/logic/filters.mjs
        qml/logic/credit.mjs
        qml/logic/days.mjs
)
target_link_libraries(gluttony_ui PRIVATE Qt6::Quick Qt6::QuickControls2)

set_target_properties(appGluttony PROPERTIES WIN32_EXECUTABLE TRUE MACOSX_BUNDLE TRUE)

# The sources include each other from the project root ("api/Api.h").
target_include_directories(appGluttony PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

target_link_libraries(appGluttony PRIVATE gluttony_uiplugin Qt6::Quick Qt6::QuickControls2 Qt6::Network)

# A dev build finds config/secrets.json in the source tree; a Release build never falls back to it.
target_compile_definitions(appGluttony PRIVATE
    $<$<NOT:$<CONFIG:Release>>:GLUTTONY_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}">
)

add_custom_command(TARGET appGluttony POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory $<TARGET_FILE_DIR:appGluttony>/config
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            ${CMAKE_CURRENT_SOURCE_DIR}/config/secrets.example.json
            $<TARGET_FILE_DIR:appGluttony>/config/secrets.example.json
)
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/config/secrets.json)
    add_custom_command(TARGET appGluttony POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                ${CMAKE_CURRENT_SOURCE_DIR}/config/secrets.json
                $<TARGET_FILE_DIR:appGluttony>/config/secrets.json
    )
endif()

option(GLUTTONY_BUILD_TESTS "Build the C++ tests" OFF)
if(GLUTTONY_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()