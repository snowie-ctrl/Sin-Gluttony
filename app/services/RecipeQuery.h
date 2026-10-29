#pragma once
#include <QObject>
#include <QString>
#include <QUrlQuery>

#include "api/Api.h"
#include "api/TileModel.h"


// One list of recipes asked of the server a page at a time: Browse's results (GET /recipes), a list's recipes
// (GET /lists/<id>/recipes) or the Devoured history (GET /devoured). The server's orders are stable, so pages are
// asked for by number. A page asked for before a new query or path is dropped when it answers, so it never lands
// in the newer list.
class RecipeQuery : public QObject
{
    Q_OBJECT

    Q_PROPERTY(QObject *tiles READ tiles CONSTANT)
    Q_PROPERTY(int count READ count NOTIFY changed)
    Q_PROPERTY(int total READ total NOTIFY changed)
    Q_PROPERTY(bool loading READ loading NOTIFY changed)
    // Every recipe that matches is shown.
    Q_PROPERTY(bool exhausted READ exhausted NOTIFY changed)
    // Why the last page failed; the rows shown stay, and more() asks for that page again.
    Q_PROPERTY(QString error READ error NOTIFY changed)
    // The first page has answered, with rows or without, so a view can tell "nothing fits" from "not asked yet".
    Q_PROPERTY(bool answered READ answered NOTIFY changed)

public:
    static constexpr int PageSize = 24;

    explicit RecipeQuery(Api &api, const QString &path = QStringLiteral("/recipes"), QObject *parent = nullptr);

    QString path() const { return m_path; }
    // Another list (another list's id, another sort): the rows go, and the next run() asks from page 1.
    void setPath(const QString &path);
    // The tile at a row, or an empty map.
    QVariantMap rowAt(int index) const { return m_model.rows().value(index).toMap(); }
    // A recipe that left the list. With every row shown it simply goes; otherwise the list is asked for again from
    // the start, since the server's later pages have each moved up by one and page by number would skip one.
    void dropRecipe(int recipeId);
    // A row dragged to another place; the server is told by whoever moved it (Saved).
    void moveRecipe(int from, int to) { m_model.moveRow(from, to); }

    QObject *tiles() { return &m_model; }
    int count() const { return m_model.rowCount(); }
    int total() const { return m_total; }
    bool loading() const { return m_loading; }
    bool exhausted() const { return m_answered && m_error.isEmpty() && m_model.rowCount() >= m_total; }
    QString error() const { return m_error; }
    bool answered() const { return m_answered; }
    QUrlQuery query() const { return m_query; }

    // A new query: the rows go and page 1 is asked for. The same query again, while it loads or once it has
    // answered without an error, changes nothing, so a page rebuilt on navigation keeps its place.
    void run(const QUrlQuery &query);
    // The same query from the start, whatever is shown (a new diet profile, Retry).
    Q_INVOKABLE void reload();
    Q_INVOKABLE void more();
    void clear();

signals:
    void changed();

private:
    void restart();
    void fetch(int page);

    Api &m_api;
    QString m_path;
    TileModel m_model;
    QUrlQuery m_query;
    bool m_hasQuery = false;
    int m_page = 0;
    int m_total = 0;
    bool m_loading = false;
    bool m_answered = false;
    QString m_error;
    int m_generation = 0;
};
