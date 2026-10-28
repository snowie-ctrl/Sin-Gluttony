#pragma once
#include <QObject>
#include <QString>
#include <QUrlQuery>
#include <QVariantList>
#include <QVariantMap>

#include "api/Api.h"
#include "services/Diet.h"
#include "services/RecipeQuery.h"


// What Browse shows: the filter panel's state, what it can offer (/filters, whole-catalog counts), the results,
// the ingredient picker, and Ctrl+K's quick search. Kept here rather than in a page, so the page is rebuilt on
// every visit and comes back as it was left. Every change asks at once: a GET per tick is cheap, and the panel
// feels live. The diet profile is the server's to apply; the catalog only passes Diet's profileParam.
class Catalog : public QObject
{
    Q_OBJECT

    Q_PROPERTY(QVariantMap filters READ filters NOTIFY filtersChanged)
    // The mood or search the results were opened with ("Quick fix", "coq"); empty for plain Browse.
    Q_PROPERTY(QString title READ title NOTIFY filtersChanged)
    Q_PROPERTY(QVariantMap options READ options NOTIFY optionsChanged)
    Q_PROPERTY(QString optionsError READ optionsError NOTIFY optionsChanged)
    Q_PROPERTY(QObject *results READ results CONSTANT)
    Q_PROPERTY(QVariantList ingredientMatches READ ingredientMatches NOTIFY ingredientMatchesChanged)
    Q_PROPERTY(QVariantList quickRecipes READ quickRecipes NOTIFY quickChanged)
    Q_PROPERTY(QVariantList quickIngredients READ quickIngredients NOTIFY quickChanged)
    Q_PROPERTY(QString quickTerm READ quickTerm NOTIFY quickChanged)
    // How many cuisines the server takes at once; the panel dims the rest once this many are ticked.
    Q_PROPERTY(int cuisineLimit READ cuisineLimit CONSTANT)

public:
    explicit Catalog(Api &api, Diet &diet, QObject *parent = nullptr);

    QVariantMap filters() const { return m_filters; }
    QString title() const { return m_title; }
    QVariantMap options() const { return m_options; }
    QString optionsError() const { return m_optionsError; }
    QObject *results() { return &m_results; }
    QVariantList ingredientMatches() const { return m_ingredientMatches; }
    QVariantList quickRecipes() const { return m_quickRecipes; }
    QVariantList quickIngredients() const { return m_quickIngredients; }
    QString quickTerm() const { return m_quickTerm; }
    static int cuisineLimit();

    // Every key the panel has, nothing narrowed.
    static QVariantMap defaultFilters();
    // What GET /recipes is sent: only what narrows, lists comma separated, in a fixed order (so the same filters
    // make the same query), and profile=off when the diet is switched off.
    static QUrlQuery wireQuery(const QVariantMap &filters, const QString &profileParam);

    Q_INVOKABLE void setFilter(const QString &key, const QVariant &value);
    // A value in a list filter: added if absent, removed if present. A cuisine past the server's limit is not added.
    Q_INVOKABLE void toggle(const QString &key, const QVariant &value);
    // key is "include" or "exclude"; an ingredient is in at most one of them, and each holds at most ten.
    Q_INVOKABLE void addIngredient(const QString &key, int id, const QString &name);
    Q_INVOKABLE void removeIngredient(const QString &key, int id);
    Q_INVOKABLE void resetFilters();
    // A mood or a dev hook: the defaults with the preset's keys, a title, and the results asked for at once.
    // A list key may be given as comma-separated text.
    Q_INVOKABLE void openWith(const QVariantMap &preset, const QString &title);
    // Results for typed text, best match first.
    Q_INVOKABLE void search(const QString &text);
    Q_INVOKABLE void apply();
    Q_INVOKABLE void loadOptions();
    Q_INVOKABLE void findIngredients(const QString &term);
    // Ctrl+K: up to six recipes and five ingredients for what is typed; under two letters, nothing is asked.
    Q_INVOKABLE void quickSearch(const QString &term);
    // Signing out: the next person starts from the defaults.
    void clear();

signals:
    void filtersChanged();
    void optionsChanged();
    void ingredientMatchesChanged();
    void quickChanged();

private:
    static QVariant normalised(const QString &key, const QVariant &value);
    void askAgain();

    Api &m_api;
    Diet &m_diet;
    QVariantMap m_filters;
    QString m_title;
    QVariantMap m_options;
    QString m_optionsError;
    RecipeQuery m_results;
    // Whether the results have been asked for at all: a diet change before then asks for nothing.
    bool m_applied = false;
    QVariantList m_ingredientMatches;
    QString m_ingredientTerm;
    QVariantList m_quickRecipes;
    QVariantList m_quickIngredients;
    QString m_quickTerm;
    // Bumped by clear(), so answers asked for by the last person are dropped.
    int m_generation = 0;
};
