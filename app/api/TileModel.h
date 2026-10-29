// Copied from Pageturner Pageturner/api/TileModel.h at ad9342e; removeRecipe and moveRow are new (lists in Saved).
#pragma once

#include <QAbstractListModel>
#include <QVariantList>
#include <QVariantMap>


// A list of tiles that grows.
//
// A plain JS array handed to a view is replaced wholesale on every update,
// which resets the view: the grid jumps back to the top and re-creates every
// delegate. Appending through a real model emits rowsInserted instead, so the
// scroll position and the delegates already on screen survive a page load.
class TileModel : public QAbstractListModel
{
    Q_OBJECT

public:
    enum Roles { TileRole = Qt::UserRole + 1 };

    explicit TileModel(QObject *parent = nullptr) : QAbstractListModel(parent) {}

    int rowCount(const QModelIndex &parent = QModelIndex()) const override
    {
        return parent.isValid() ? 0 : int(m_rows.size());
    }

    QVariant data(const QModelIndex &index, int role) const override
    {
        if (!index.isValid() || index.row() < 0 || index.row() >= m_rows.size())
            return {};
        if (role != TileRole)
            return {};
        return m_rows.at(index.row());
    }

    QHash<int, QByteArray> roleNames() const override
    {
        return { { TileRole, QByteArrayLiteral("tile") } };
    }

    void appendRows(const QVariantList &rows)
    {
        if (rows.isEmpty())
            return;

        beginInsertRows(QModelIndex(), int(m_rows.size()),
                        int(m_rows.size() + rows.size()) - 1);
        m_rows.append(rows);
        endInsertRows();
    }

    void clearRows()
    {
        if (m_rows.isEmpty())
            return;

        beginResetModel();
        m_rows.clear();
        endResetModel();
    }

    // Takes out the row of this recipe (rows are tiles with an "id"); true when one was there.
    bool removeRecipe(int recipeId)
    {
        for (int i = 0; i < m_rows.size(); ++i) {
            if (m_rows.at(i).toMap().value("id").toInt() != recipeId)
                continue;
            beginRemoveRows(QModelIndex(), i, i);
            m_rows.removeAt(i);
            endRemoveRows();
            return true;
        }
        return false;
    }

    // One row to another place, as a drag leaves it. A move, not a reset, so the view keeps its delegates.
    void moveRow(int from, int to)
    {
        const int size = int(m_rows.size());
        if (from == to || from < 0 || to < 0 || from >= size || to >= size)
            return;
        // beginMoveRows names the row the moved one goes before, counted before the move.
        beginMoveRows(QModelIndex(), from, from, QModelIndex(), to > from ? to + 1 : to);
        m_rows.move(from, to);
        endMoveRows();
    }

    QVariantList rows() const { return m_rows; }

private:
    QVariantList m_rows;
};
