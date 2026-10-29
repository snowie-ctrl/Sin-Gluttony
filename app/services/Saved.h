#pragma once
#include <QHash>
#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QString>
#include <QVariantList>
#include <QVariantMap>

#include "api/Api.h"
#include "services/RecipeQuery.h"


// What a person keeps: their lists (Cravings first, then their own, in their order), the recipes on them, and
// what they keep on the recipe that is open (`mine`, from GET /recipes/<id>). Every change is asked of the server
// and shown once it answers, in the server's words when it refuses.
//
// Tiles come from many answers (Results, Home, lists, Seconds?), each with the flags the server knew then. A change
// made here is kept in an overlay that every tile reads through flagsOf(), so a ♥ made on the recipe page shows on
// every tile at once without asking for any of them again.
class Saved : public QObject
{
    Q_OBJECT

    // [{id, title, kind, count}], Cravings first.
    Q_PROPERTY(QVariantList lists READ lists NOTIFY listsChanged)
    Q_PROPERTY(int cravingsId READ cravingsId NOTIFY listsChanged)
    Q_PROPERTY(bool listsLoaded READ listsLoaded NOTIFY listsChanged)
    // Why the last load failed; the lists shown stay.
    Q_PROPERTY(QString listsError READ listsError NOTIFY listsChanged)
    // Fewer than the server's 50 lists (Cravings counts), so "New list" can be offered.
    Q_PROPERTY(bool canCreateList READ canCreateList NOTIFY listsChanged)
    Q_PROPERTY(int listLimit READ listLimit CONSTANT)
    Q_PROPERTY(int titleLimit READ titleLimit CONSTANT)
    // The list the Saved page shows, and its recipes a page at a time.
    Q_PROPERTY(int openListId READ openListId NOTIFY openListChanged)
    Q_PROPERTY(QObject *listRecipes READ listRecipes CONSTANT)
    // Bumped whenever the overlay changes, so bindings that call flagsOf() are evaluated again.
    Q_PROPERTY(int flagsRevision READ flagsRevision NOTIFY flagsChanged)
    // The recipe open on the recipe page, and what this person keeps on it.
    Q_PROPERTY(int mineId READ mineId NOTIFY mineChanged)
    Q_PROPERTY(QVariantMap mine READ mine NOTIFY mineChanged)
    // A list being made, renamed or deleted: the popups wait for it.
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    // Every time the person made something, one tile per mark (GET /devoured), newest first or by their stars.
    Q_PROPERTY(QObject *devouredHistory READ devouredHistory CONSTANT)
    Q_PROPERTY(QString devouredSort READ devouredSort NOTIFY devouredSortChanged)
    // The Saved page's open tab is Devoured rather than a list; kept here because the page is rebuilt every visit.
    Q_PROPERTY(bool devouredOpen READ devouredOpen NOTIFY openListChanged)
    Q_PROPERTY(int noteLimit READ noteLimit CONSTANT)
    // A Devoured mark is on its way: a second tap waits for it rather than counting twice.
    Q_PROPERTY(bool devouring READ devouring NOTIFY devouringChanged)
    // The ids of the recipes whose stars, or whose note, are on their way to the server. Requests are not serialised,
    // so two quick ones could be answered in either order and leave what is shown unlike what the server holds: the
    // recipe page rests the stars, and the note's Save, while their recipe is in the list.
    Q_PROPERTY(QVariantList starsSaving READ starsSaving NOTIFY savingChanged)
    Q_PROPERTY(QVariantList noteSaving READ noteSaving NOTIFY savingChanged)

public:
    static constexpr int ListLimit = 50;
    static constexpr int TitleLimit = 60;
    static constexpr int NoteLimit = 2000;

    explicit Saved(Api &api, QObject *parent = nullptr);

    QVariantList lists() const { return m_lists; }
    int cravingsId() const { return m_cravingsId; }
    bool listsLoaded() const { return m_listsLoaded; }
    QString listsError() const { return m_listsError; }
    bool canCreateList() const { return m_listsLoaded && m_lists.size() < ListLimit; }
    static int listLimit() { return ListLimit; }
    static int titleLimit() { return TitleLimit; }
    int openListId() const { return m_openListId; }
    QObject *listRecipes() { return &m_listRecipes; }
    int flagsRevision() const { return m_flagsRevision; }
    int mineId() const { return m_mineId; }
    QVariantMap mine() const { return m_mine; }
    bool busy() const { return m_pending > 0; }
    QObject *devouredHistory() { return &m_history; }
    QString devouredSort() const { return m_sort; }
    bool devouredOpen() const { return m_devouredOpen; }
    static int noteLimit() { return NoteLimit; }
    bool devouring() const { return m_devouring; }
    QVariantList starsSaving() const;
    QVariantList noteSaving() const;

    // A note as the server keeps it: trimmed. Its length is counted in code points, as the server and MySQL count
    // characters; Qt's own size() counts an emoji twice.
    static QString cleanNote(const QString &text) { return text.trimmed(); }
    Q_INVOKABLE int noteLength(const QString &text) const { return int(cleanNote(text).toUcs4().size()); }
    // This device's calendar day, "YYYY-MM-DD": the day a person means by "today", whatever the server's zone.
    Q_INVOKABLE QString today() const;

    // A title as the server takes it: trimmed, 1 to 60 characters counted as the server counts them (an emoji is
    // one); empty when the server would refuse it.
    static QString cleanTitle(const QString &title);

    Q_INVOKABLE void load();
    // A new list at the end; with addRecipeId, that recipe goes on it once it exists (+ List's "New list").
    Q_INVOKABLE void createList(const QString &title, int addRecipeId = 0);
    Q_INVOKABLE void renameList(int listId, const QString &title);
    Q_INVOKABLE void deleteList(int listId);
    // One of the person's own lists, `steps` places earlier (negative) or later; Cravings stays first.
    Q_INVOKABLE void moveList(int listId, int steps);
    // The Saved page's tab: its recipes are asked for, unless they are already shown and nothing has changed.
    Q_INVOKABLE void openList(int listId);
    Q_INVOKABLE void setCraving(int recipeId, bool craving);
    Q_INVOKABLE void setInList(int listId, int recipeId, bool in);
    // A tile of the open list dragged from one row to another. The grid moves at once; the server is told what the
    // recipe now follows, one move at a time, in the order they were made.
    Q_INVOKABLE void moveItem(int from, int to);
    // A tile's {craving, devouredCount, stars}: what its answer said, with this session's changes over it.
    Q_INVOKABLE QVariantMap flagsOf(const QVariantMap &tile) const;
    Q_INVOKABLE QString listTitle(int listId) const;
    // One more time made, on `day` ("YYYY-MM-DD", today or before). The mark carries a new id of the app's own, so
    // the server stores it once however often it is sent.
    Q_INVOKABLE void devour(int recipeId, const QString &day);
    Q_INVOKABLE void undevour(int markId);
    // 1 to 5; 0 clears them.
    Q_INVOKABLE void setStars(int recipeId, int stars);
    // Empty text deletes the note.
    Q_INVOKABLE void setNote(int recipeId, const QString &text);
    // The Devoured tab, "recent" or "stars": asked for unless already shown and unchanged since.
    Q_INVOKABLE void openDevoured(const QString &sort);

    // The recipe page opened another recipe, or its detail arrived (recipeId 0: none open).
    void showMine(int recipeId, const QVariantMap &mine);
    // Signing out: nothing of this person's is left for the next one, and no answer for them lands.
    void clear();

signals:
    void listsChanged();
    void openListChanged();
    void flagsChanged();
    void mineChanged();
    void busyChanged();
    void devouredSortChanged();
    void devouringChanged();
    void savingChanged();
    void listCreated(int listId);
    // A change asked for has been made (what as in failed()), so a popup that asked for it can close.
    void done(const QString &what);
    // what: "lists", "list", "item" or "move" (and, from the Devoured work, "devoured", "stars", "note").
    void failed(const QString &what, const QString &message);
    // Cravings or the Devoured marks changed, so what Home shows of them is out of date.
    void keptChanged();

private:
    int indexOfList(int listId) const;
    void setCount(int listId, int count);
    void noteFlag(int recipeId, const QString &key, const QVariant &value);
    // A move of a list or of a recipe on the open list, waiting for its turn.
    struct Move
    {
        QString route;
        QJsonObject body;
        bool ofList = false;
    };
    void queueMove(const Move &move);
    void sendNextMove();
    void beginEdit();
    void endEdit();
    void setDevouring(bool devouring);
    // A star or note request for this recipe went out (on) or came back, in any way.
    void markSaving(QList<int> &list, int recipeId, bool on);

    Api &m_api;
    QVariantList m_lists;
    int m_cravingsId = 0;
    bool m_listsLoaded = false;
    QString m_listsError;
    int m_openListId = 0;
    // A recipe was added to the open list since it was shown, so the next openList asks again.
    bool m_openStale = false;
    RecipeQuery m_listRecipes;
    QHash<int, QVariantMap> m_flags;
    int m_flagsRevision = 0;
    int m_mineId = 0;
    QVariantMap m_mine;
    QList<Move> m_moves;
    bool m_moving = false;
    RecipeQuery m_history;
    QString m_sort = QStringLiteral("recent");
    // A mark or a star changed since the history was shown, so the next openDevoured asks again.
    bool m_historyStale = false;
    bool m_devouring = false;
    bool m_devouredOpen = false;
    // One entry per request on its way, so two for the same recipe are both counted.
    QList<int> m_starsSaving;
    QList<int> m_noteSaving;
    int m_pending = 0;
    // Bumped by clear(), so an answer meant for the last person is dropped.
    int m_generation = 0;
};
