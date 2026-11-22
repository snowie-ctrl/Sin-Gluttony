#pragma once

#include <QtGlobal>

// The QML engine's garbage collector runs each collection to the end in one go, as before Qt 6.8, rather than in
// slices between event-loop turns. With the slices (Qt 6.11.1) the recipe page lost track of a live JS object when
// a recipe arrived mid-collection and the debug build stopped on a heap assertion (found with the glossary's extra
// allocations; a page with no glossary at all hit it once the timing lined up). Whole collections are a few
// milliseconds in an app this size. Call before any QML engine exists; an owner's own QV4_GC_TIMELIMIT wins.
inline void useWholeGarbageCollections()
{
    if (!qEnvironmentVariableIsSet("QV4_GC_TIMELIMIT"))
        qputenv("QV4_GC_TIMELIMIT", "0");
}
