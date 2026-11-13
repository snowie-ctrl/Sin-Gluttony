# Gluttony: look reset (icon and Ember palette)

Status: designed with the owner 2026-11-13 (palette chosen from three mockups). Waiting for the
owner's review of this file.

Part 2 (`2026-10-27-app-core-design.md`) shipped the "Gula" look: orange molten into crimson on a
dark chocolate ground. In daily use it is tiring to look at, and the warm brown chrome makes the
food pictures look dull and brown. Part 2 also drew its own mark (`gluttony.svg`) instead of using
the premade Gluttony icon that the sin apps share. This reset fixes both. It is built before the
new catalog (`2026-11-13-new-catalog-design.md`) and does not depend on it.

## Decisions

| Topic | Decision |
|---|---|
| Icon | The premade `gluttonyAppIcon.png` (orange pig snout on a black rounded square, from the owner's `sinAppLogos` folder) is Gluttony's only mark. `gluttony.svg` is deleted. |
| Palette | "Ember": a neutral charcoal, near-monochrome dark theme. Gluttony lives only in the accents: the icon's orange melting into crimson as the gradient, with amber and rose as extra accents. |
| Pictures | Sit on plain neutral grey. No warm tint anywhere near the food. |
| Kept as is | Layouts, mood starters, the tag set, Playfair Display headings, the cheeky voice (`words.mjs`), radii, spacing. |

## 1. Icon

- Copy `gluttonyAppIcon.png` into `app/assets/images/` and list it in `resources.qrc`.
- Generate `app/assets/gluttony.ico` from it with sizes 16, 24, 32, 48, 64, 128 and 256 px, and
  add `app/assets/gluttony.rc` (`IDI_ICON1 ICON "gluttony.ico"`) to the Windows executable's
  sources in `app/CMakeLists.txt`. Today the exe has no icon at all; after this the exe, the
  taskbar, Alt-Tab and the release zip all show the pig.
- `main.cpp` sets the window icon from the PNG instead of `:/images/gluttony.svg`.
- The rail mark (`NavShell.qml`) and the sign-in page (`LoginPage.qml`) show the PNG at their
  current sizes, rendered with `smooth` and `mipmap` so it stays crisp when scaled down. It is a
  full-colour picture, so it is shown as an `Image`, not through `TintedIcon`.
- Delete `app/assets/images/gluttony.svg` and its qrc entry.
- `release.ps1` needs no change beyond picking up the new exe; its package check confirms the exe
  still starts.

## 2. Ember tokens

These replace the token table in part 2's section 7. The orange is sampled from the icon during
the build; the other values may be nudged on screen by a few steps, but they stay neutral (equal or
near-equal R, G and B) for every ground, border and text token.

| token | old (Gula) | Ember | used for |
|---|---|---|---|
| `backgroundPrimary` | `#140c08` | `#0f0f11` | the page behind everything |
| `backgroundSecondary` | `#22140d` | `#17171a` | panels, the rail, the top bar, mood cards |
| `backgroundTertiary` | `#2e1b12` | `#222226` | fields, pills, hovered rows |
| `surfaceArt` | `#161312` | `#1c1c1f` | the ground under every picture |
| `borderColor` | `#3a2418` | `#2c2c31` | hairlines, field borders, dividers |
| `textPrimary` | `#fbeee2` | `#f4f4f5` | body and headings |
| `textSecondary` | `#d8b9a0` | `#b4b4bb` | supporting text |
| `textMuted` | `#9a7a64` | `#7d7d86` | placeholders, metadata, counts |
| `accentColor` | `#ff7a1a` | the icon's orange (about `#ff7a1a`) | focus, selection, the active rail item, gradient start |
| `accentDeep` | `#c8212f` | `#e8263f` | gradient end |
| `accentSubtle` | `#3a1a0d` | `#2b1d16` | accent-tinted grounds: a selected chip, the active rail pill |
| `accentAmber` | (new) | `#ffc24b` | time and effort chips |
| `accentRose` | (new) | `#ff5470` | flavour and heat chips |
| `dangerColor` | `#e23d3d` | `#f04444` | errors and destructive actions |
| `successColor` | `#6fbf73` | `#4fd18b` | ticks, Devoured |

## 3. Where colour goes

- **Gradient** (`accentColor` → `accentDeep`): primary actions, mood tiles and the "Today's
  temptation" badge, as in part 2. Nowhere else.
- **Chip families**, outlined chips with text and border in the family colour (border at about
  35% opacity), filled with `accentSubtle` when selected:
  - orange (`accentColor`): moods and cravings, course, cuisine, occasion
  - rose (`accentRose`): flavour (sweet, savoury, spicy, sour, bitter) and anything about heat
  - amber (`accentAmber`): time and effort ("Quick", minutes, difficulty)
  - diet and allergen chips stay neutral (`textSecondary` on `backgroundTertiary`) so safety
    information never reads as decoration
  The family is chosen from the filter kind that the chip already carries; the plan lists the
  exact kind-to-family map from `Chip.qml`'s callers.
- **Headings** are `textPrimary`, not orange. Orange marks only what is active or selected. (Part
  2 coloured headings with the accent; that is a large part of why the old look was tiring.)
- Destructive buttons stay outlined in `dangerColor` and named in words, never gradient-filled.
- Pictures sit on `surfaceArt`, as before, and nothing tints them.

## 4. Stored colours

`Preferences` stores only values a person changed (a value equal to its default is not written).
To make sure nobody keeps a brown leftover from Gula, a `paletteVersion` key is added. On start,
when the stored version is below 2, every stored colour key is removed (the same keys
`resetColours()` finds) and the version is set to 2. Non-colour preferences are untouched.

## 5. Testing and checks

- `tst_preferences`: the Ember defaults, the two new tokens, and the version bump (stored Gula
  colours are cleared once; a colour changed after the bump survives a restart).
- The existing QML tests pass unchanged except where they assert old hex values or the old icon
  path, which are updated.
- The package check in `release.ps1` passes, and the built exe shows the pig in Explorer.
- Before/after screenshots of Home, Results (filter panel open), Recipe, Cook and Sign-in go to the
  owner for a look on the real screen. That look is the acceptance check for the palette.

## Done when

The exe, window, rail and sign-in page show the premade icon; every screen uses the Ember tokens;
chip families read in orange, rose and amber; old stored colours are gone; tests pass; and the owner
has looked at the screenshots and said yes.
