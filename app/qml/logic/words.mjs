// Every word Gluttony shows, in one place, so the app's voice can be changed in one file. The voice is cheeky
// and indulgent; where something went wrong, the words stay plain.

export const appName = "Gluttony"
export const navHome = "Home"
export const navBrowse = "Browse"
export const searchPlaceholder = "What are you hungry for?"
export const searchRecipes = "Recipes"
export const searchIngredients = "Ingredients"
export const searchWith = "Recipes with "
export const searchAll = "See everything for "
export const todaysTemptation = "Today's temptation"
export const todaysPicks = "Today's picks"
export const cravings = "Cravings"
export const cravingsHint = "the ones you keep coming back to"
export const again = "Again?"
export const againHint = "what you devoured lately"
export const goOnThen = "Go on, then"
export const seconds = "Seconds?"
export const secondsHint = "Other ways to make this"
export const browseTitle = "Browse"
export const ingredientsTitle = "Ingredients"
export const methodTitle = "Method"
export const optional = "optional"
export const servingsWord = "servings"
export const metric = "Metric"
export const us = "US"
export const about = "about "
export const showOriginal = "As written: "
export const loadingWords = "Setting the table…"
export const tryAgain = "Try again"
export const back = "Back"
export const filtersTitle = "Filters"
export const resetFilters = "Reset"
export const sortTitle = "Sort"
export const showAll = "Show all"
export const typeAnIngredient = "Type an ingredient"
export const nothingFitsDiet = "Nothing fits your diet"
export const nothingFitsDietHint = "Switch your diet off for now to see everything."
export const switchDietOff = "Switch it off for now"
export const nothingFits = "Nothing fits these filters"
export const nothingFitsHint = "Loosen a filter, or switch your diet off for this search."
export const goOnThenNothing = "Nothing fits your diet right now."
export const gone = "This recipe has gone from the catalog"
export const goneHint = "Its source no longer has it."
export const offline = "You're offline: the server can't be reached."
export const unknownIngredients = "Some ingredients unknown, may not suit your diet"
export const creditSource = "Source"
export const creditPicture = "Picture: "
export const creditVideo = "Video"
export const dietTitle = "Your diet"
export const dietDiets = "I eat"
export const dietAvoid = "I avoid"
export const dietEdit = "Edit"
export const dietSave = "Save"
export const dietCancel = "Cancel"
export const dietOn = "On"
export const dietOffForNow = "Off for now"
export const dietNone = "No diet set"
export const dietLoadFailed = "Your diet could not be loaded"
export const signInTitle = "Gluttony"
export const signInTagline = "Go on. Have seconds."
export const username = "Username"
export const password = "Password"
export const signUpKey = "Sign-up key"
export const haveAKey = "I have a sign-up key"
export const signIn = "Sign in"
export const createAccount = "Create account"
export const signingIn = "Signing in…"
export const enterUsernameAndPassword = "Enter your username and password"
export const enterKey = "Enter your sign-up key"
export const unreachable = "The server can't be reached"
export const signOut = "Sign out"
export const today = "today"
export const yesterday = "yesterday"
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
export const goneFromSource = "gone from its source"
export const goneNote = "Gone from its source. It stays yours to open."
export const craving = "Craving"
export const addToList = "List"
export const devoured = "Devoured"
export const note = "Note"
export const editNote = "Edit note"
export const noteTitle = "Your note"
export const noteHint = "Only you see this."
export const save = "Save"
export const cancel = "Cancel"
export const newList = "New list"
export const create = "Create"
export const yourLists = "Your lists"
export const noListsYet = "No lists of your own yet."
export const earlier = "‹"
export const later = "›"

// The diet and avoid words match the server's lists (server/gluttonyRules.py DIETS and CONTAINS_ITEMS).
export const DIETS = [
    { value: "vegetarian", label: "Vegetarian" }, { value: "vegan", label: "Vegan" },
    { value: "gluten-free", label: "Gluten-free" }, { value: "dairy-free", label: "Dairy-free" }
]
// Avoid items as a person says them after "no".
export const AVOID = [
    { value: "meat", label: "meat" }, { value: "poultry", label: "poultry" }, { value: "fish", label: "fish" },
    { value: "shellfish", label: "shellfish" }, { value: "dairy", label: "dairy" }, { value: "egg", label: "eggs" },
    { value: "gluten", label: "gluten" }, { value: "tree-nut", label: "tree nuts" }, { value: "peanut", label: "peanuts" },
    { value: "soy", label: "soy" }, { value: "sesame", label: "sesame" }, { value: "alcohol", label: "alcohol" },
    { value: "honey", label: "honey" }
]
export const KINDS = [{ value: "", label: "Both" }, { value: "food", label: "Food" }, { value: "drink", label: "Drink" }]
export const TIMES = [{ value: 15, label: "15 min" }, { value: 30, label: "30 min" }, { value: 60, label: "1 hour" },
                      { value: 0, label: "Any" }]
export const EFFORTS = [{ value: 1, label: "Easy" }, { value: 2, label: "Medium" }, { value: 3, label: "Involved" }]
export const ALCOHOL = [{ value: "alcoholic", label: "Alcoholic" }, { value: "non-alcoholic", label: "Alcohol-free" },
                        { value: "optional", label: "Either way" }]
export const SORTS = [{ value: "shuffle", label: "Daily shuffle" }, { value: "quickest", label: "Quickest" },
                      { value: "relevance", label: "Best match" }]
export const FILTER_TITLES = {
    diet: "Your diet", kind: "Food or drink", time: "Time", effort: "Effort", course: "Course", cuisine: "Cuisine",
    flavour: "Taste", occasion: "Occasion", alcohol: "Alcohol", avoid: "Avoid", include: "Must include",
    exclude: "Leave out"
}
export const MOOD_WORDS = {
    quick: { title: "Quick fix", hint: "30 min or less, easy" },
    crowd: { title: "Feed a crowd", hint: "for a party" },
    sweet: { title: "Sweet tooth", hint: "desserts" },
    drinks: { title: "Bottoms up", hint: "cocktails and mocktails" }
}

function labelOf(list, value) {
    const found = list.find(item => item.value === value)
    return found ? found.label : value
}

export function dietChip(diets, avoid) {
    const parts = (diets || []).map(d => labelOf(DIETS, d))
    if (avoid && avoid.length)
        parts.push("no " + avoid.map(a => labelOf(AVOID, a)).join(", "))
    return parts.join(" · ")
}

export function effortWord(difficulty) {
    return ({ 1: "easy", 2: "medium", 3: "involved" })[difficulty] || ""
}

export function courseWord(course) {
    return course === "coffee/tea" ? "coffee or tea" : (course || "")
}

export function sourceName(source) {
    return ({ mealdb: "TheMealDB", cocktaildb: "TheCocktailDB", wikibooks: "Wikibooks" })[source] || (source || "")
}

export function recipeCount(n) {
    return n === 1 ? "1 recipe" : n + " recipes"
}

export function servingsText(n, from) {
    if (!(n > 0))
        return ""
    return (from === "rule" ? about : "") + n + (n === 1 ? " serving" : " servings")
}

export function containsText(items) {
    return items && items.length ? "contains " + items.join(", ") : ""
}

export function signedInAs(name) {
    return "Signed in as " + name
}

// A tile's ✓ badge: a tick, and how many times when more than once.
export function devouredBadge(count) {
    return count > 0 ? "✓" + (count > 1 ? count : "") : ""
}

export function starsBadge(stars) {
    return stars > 0 ? "★" + stars : ""
}

// The note editor's count, in characters as the server counts them.
export function noteCount(n, limit) {
    return n + " / " + limit
}
