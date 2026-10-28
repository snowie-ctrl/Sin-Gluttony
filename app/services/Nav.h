// Copied from Pageturner Pageturner/services/Nav.h at ad9342e; Gluttony's pages; no sign-out flow (nothing is
// queued in milestone 1).
#pragma once
#include <QObject>
#include <QString>


// Which page is showing. Main.qml swaps the top-level page (sign-in, the shell) by name and the shell swaps its
// own pages; both listen to changePage. Kept apart from the services so none of them knows about pages.
class Nav : public QObject
{
    Q_OBJECT

    Q_PROPERTY(QString currentPage READ currentPage NOTIFY changePage)
    // Where signing in lands: Home normally; grab.ps1 points it elsewhere to photograph a page.
    Q_PROPERTY(QString startPage READ startPage WRITE setStartPage NOTIFY startPageChanged)

public:
    using QObject::QObject;

    QString currentPage() const { return m_currentPage; }
    QString startPage() const { return m_startPage; }
    void setStartPage(const QString &page)
    {
        if (page == m_startPage)
            return;
        m_startPage = page;
        emit startPageChanged();
    }

    Q_INVOKABLE void navigateTo(const QString &page)
    {
        m_currentPage = page;
        if (page == QLatin1String("login-page") || page == QLatin1String("nav-shell")) {
            emit changePage(page);
            return;
        }
        // The shell has to exist before it can take one of its own pages; a shell being built starts on
        // currentPage, so it lands on this one.
        emit changePage(QStringLiteral("nav-shell"));
        emit changePage(page);
    }

signals:
    void changePage(const QString &page);
    void startPageChanged();

private:
    QString m_currentPage = QStringLiteral("login-page");
    QString m_startPage = QStringLiteral("home-page");
};
