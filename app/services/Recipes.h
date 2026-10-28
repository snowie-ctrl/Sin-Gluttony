#pragma once
#include <QObject>
#include <QString>
#include <QVariantMap>

#include "api/Api.h"


// The recipe being looked at: its detail (GET /recipes/<id>), and the servings or multiplier chosen for it on
// this visit. Cook mode (milestone 3) reads the same choices. A recipe that has gone from the catalog (404) says
// so rather than failing.
class Recipes : public QObject
{
    Q_OBJECT

    Q_PROPERTY(int recipeId READ recipeId NOTIFY changed)
    Q_PROPERTY(QVariantMap recipe READ recipe NOTIFY changed)
    Q_PROPERTY(bool loading READ loading NOTIFY changed)
    Q_PROPERTY(bool gone READ gone NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    // The servings chosen (1 to 99); 0 when the recipe states none, which scales by `multiplier` instead.
    Q_PROPERTY(int servings READ servings WRITE setServings NOTIFY servingsChanged)
    Q_PROPERTY(double multiplier READ multiplier WRITE setMultiplier NOTIFY servingsChanged)

public:
    explicit Recipes(Api &api, QObject *parent = nullptr);

    int recipeId() const { return m_recipeId; }
    QVariantMap recipe() const { return m_recipe; }
    bool loading() const { return m_loading; }
    bool gone() const { return m_gone; }
    QString error() const { return m_error; }
    int servings() const { return m_servings; }
    double multiplier() const { return m_multiplier; }
    void setServings(int servings);
    void setMultiplier(double multiplier);

    // A new recipe starts from its own servings; the one already open and loaded is left as it is.
    Q_INVOKABLE void open(int recipeId);
    Q_INVOKABLE void reload();
    Q_INVOKABLE QString thumbUrl(int recipeId) const { return m_api.pictureUrl(QStringLiteral("thumbs"), recipeId); }
    Q_INVOKABLE QString imageUrl(int recipeId) const { return m_api.pictureUrl(QStringLiteral("images"), recipeId); }
    void clear();

signals:
    void changed();
    void servingsChanged();

private:
    void fetch();

    Api &m_api;
    int m_recipeId = -1;
    QVariantMap m_recipe;
    bool m_loading = false;
    bool m_gone = false;
    QString m_error;
    int m_servings = 0;
    double m_multiplier = 1.0;
    int m_generation = 0;
};
