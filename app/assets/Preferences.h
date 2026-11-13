// Copied from Pageturner Pageturner/assets/Preferences.h at ad9342e; Gluttony's look ("Ember") replaces the
// ink-blue tokens; the reader, storage and per-series settings are gone; units, tileWidth, the filter panel and
// resetColours are new.
#pragma once
#include <QColor>
#include <QObject>
#include <QStringList>
#include <QTimer>
#include <QVariantMap>


// Every look and per-device choice, saved as an ini under %APPDATA%\Gluttony. Properties are found by
// reflection, so a new MEMBER is saved, clamped and resettable with no extra wiring.
class Preferences : public QObject
{
    Q_OBJECT

        // Type
    Q_PROPERTY(QString appFont            MEMBER appFont            NOTIFY appFontChanged)
    Q_PROPERTY(QString headingFont        MEMBER headingFont        NOTIFY headingFontChanged)
    Q_PROPERTY(int     fontSizeDisplay    MEMBER fontSizeDisplay    NOTIFY fontSizeDisplayChanged)
    Q_PROPERTY(int     fontSizeHeading    MEMBER fontSizeHeading    NOTIFY fontSizeHeadingChanged)
    Q_PROPERTY(int     fontSizeBody       MEMBER fontSizeBody       NOTIFY fontSizeBodyChanged)
    Q_PROPERTY(int     fontSizeLabel      MEMBER fontSizeLabel      NOTIFY fontSizeLabelChanged)
    Q_PROPERTY(int     fontSizeCaption    MEMBER fontSizeCaption    NOTIFY fontSizeCaptionChanged)
        // Shape and spacing
    Q_PROPERTY(int     cornerRadius       MEMBER cornerRadius       NOTIFY cornerRadiusChanged)
    Q_PROPERTY(int     controlRadius      MEMBER controlRadius      NOTIFY controlRadiusChanged)
    Q_PROPERTY(int     spacingSmall       MEMBER spacingSmall       NOTIFY spacingSmallChanged)
    Q_PROPERTY(int     spacingMedium      MEMBER spacingMedium      NOTIFY spacingMediumChanged)
    Q_PROPERTY(int     spacingLarge       MEMBER spacingLarge       NOTIFY spacingLargeChanged)
        // Colour
    Q_PROPERTY(QColor  backgroundPrimary   MEMBER backgroundPrimary   NOTIFY backgroundPrimaryChanged)
    Q_PROPERTY(QColor  backgroundSecondary MEMBER backgroundSecondary NOTIFY backgroundSecondaryChanged)
    Q_PROPERTY(QColor  backgroundTertiary  MEMBER backgroundTertiary  NOTIFY backgroundTertiaryChanged)
    Q_PROPERTY(QColor  surfaceArt          MEMBER surfaceArt          NOTIFY surfaceArtChanged)
    Q_PROPERTY(QColor  accentColor         MEMBER accentColor         NOTIFY accentColorChanged)
    Q_PROPERTY(QColor  accentDeep          MEMBER accentDeep          NOTIFY accentDeepChanged)
    Q_PROPERTY(QColor  accentSubtle        MEMBER accentSubtle        NOTIFY accentSubtleChanged)
    Q_PROPERTY(QColor  accentAmber         MEMBER accentAmber         NOTIFY accentAmberChanged)
    Q_PROPERTY(QColor  accentRose          MEMBER accentRose          NOTIFY accentRoseChanged)
    Q_PROPERTY(QColor  borderColor         MEMBER borderColor         NOTIFY borderColorChanged)
    Q_PROPERTY(QColor  textPrimary         MEMBER textPrimary         NOTIFY textPrimaryChanged)
    Q_PROPERTY(QColor  textSecondary       MEMBER textSecondary       NOTIFY textSecondaryChanged)
    Q_PROPERTY(QColor  textMuted           MEMBER textMuted           NOTIFY textMutedChanged)
    Q_PROPERTY(QColor  dangerColor         MEMBER dangerColor         NOTIFY dangerColorChanged)
    Q_PROPERTY(QColor  successColor        MEMBER successColor        NOTIFY successColorChanged)
        // Browsing and recipes
    Q_PROPERTY(QString units               MEMBER units               NOTIFY unitsChanged)
    Q_PROPERTY(int     tileWidth           MEMBER tileWidth           NOTIFY tileWidthChanged)
    Q_PROPERTY(bool    filterPanelCollapsed MEMBER filterPanelCollapsed NOTIFY filterPanelCollapsedChanged)
        // Settings page
    Q_PROPERTY(QVariantMap defaults READ defaults CONSTANT)
    Q_PROPERTY(QString storagePath READ storagePath CONSTANT)

public:
    explicit Preferences(QObject *parent = nullptr);
    ~Preferences() override;

    QVariantMap defaults() const { return m_defaults; }
    QString storagePath() const;
    Q_INVOKABLE QVariantMap limits(const QString &key) const;
    Q_INVOKABLE QStringList choices(const QString &key) const;
    Q_INVOKABLE void reset(const QString &key);
    Q_INVOKABLE void resetAll();
    // Settings › Colours: every colour token back to Ember's, everything else as it is.
    Q_INVOKABLE void resetColours();

        // Type: Tahoma for reading, Playfair Display (bundled) for headings, mood names and page titles.
    QString appFont =           QStringLiteral("Tahoma");
    QString headingFont =       QStringLiteral("Playfair Display");
    int     fontSizeDisplay =   26;   // a page's own title, a recipe's title
    int     fontSizeHeading =   18;   // section and row headings
    int     fontSizeBody =      14;   // body text, list rows, buttons
    int     fontSizeLabel =     13;   // tile titles, field labels
    int     fontSizeCaption =   12;   // metadata, counts
        // Shape and spacing
    int     cornerRadius =      12;   // cards, tiles, the hero
    int     controlRadius =     8;    // buttons and fields; chips are fully round
    int     spacingSmall =      8;
    int     spacingMedium =     16;
    int     spacingLarge =      24;
        // Colour ("Ember"). Neutral charcoal grounds and neutral text; Gluttony lives only in the accents, the icon's
        // orange melting into crimson. Pictures sit on surfaceArt and nothing tints them.
    QColor  backgroundPrimary =   QColor(0x0f0f11); // the page behind everything
    QColor  backgroundSecondary = QColor(0x17171a); // panels, the rail, the top bar, mood cards
    QColor  backgroundTertiary =  QColor(0x222226); // fields, pills, hovered rows
    QColor  surfaceArt =          QColor(0x1c1c1f); // under every picture
    QColor  accentColor =         QColor(0xf27620); // the icon's orange: focus, selection; the gradient's start
    QColor  accentDeep =          QColor(0xe8263f); // the gradient's end
    QColor  accentSubtle =        QColor(0x2b1d16); // a selected chip, the active rail pill
    QColor  accentAmber =         QColor(0xffc24b); // time and effort chips
    QColor  accentRose =          QColor(0xff5470); // flavour chips
    QColor  borderColor =         QColor(0x2c2c31); // hairlines, field borders
    QColor  textPrimary =         QColor(0xf4f4f5); // body and headings
    QColor  textSecondary =       QColor(0xb4b4bb);
    QColor  textMuted =           QColor(0x7d7d86); // placeholders, metadata, counts
    QColor  dangerColor =         QColor(0xf04444); // errors; destructive buttons are outlined in it
    QColor  successColor =        QColor(0x4fd18b);
        // Browsing and recipes
    QString units =             QStringLiteral("metric");   // metric | us
    int     tileWidth =         200;
    bool    filterPanelCollapsed = false;

signals:
    void appFontChanged();
    void headingFontChanged();
    void fontSizeDisplayChanged();
    void fontSizeHeadingChanged();
    void fontSizeBodyChanged();
    void fontSizeLabelChanged();
    void fontSizeCaptionChanged();
    void cornerRadiusChanged();
    void controlRadiusChanged();
    void spacingSmallChanged();
    void spacingMediumChanged();
    void spacingLargeChanged();
    void backgroundPrimaryChanged();
    void backgroundSecondaryChanged();
    void backgroundTertiaryChanged();
    void surfaceArtChanged();
    void accentColorChanged();
    void accentDeepChanged();
    void accentSubtleChanged();
    void accentAmberChanged();
    void accentRoseChanged();
    void borderColorChanged();
    void textPrimaryChanged();
    void textSecondaryChanged();
    void textMutedChanged();
    void dangerColorChanged();
    void successColorChanged();
    void unitsChanged();
    void tileWidthChanged();
    void filterPanelCollapsedChanged();

private slots:
    void scheduleSave();

private:
    void load();
    void save();
    QVariant clamped(const QString &key, const QVariant &value) const;

    QVariantMap m_defaults;
    QTimer m_saveTimer;
};
