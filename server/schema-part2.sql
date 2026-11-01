-- Gluttony part 2: accounts and what each person keeps, beside part 1's catalog tables (schema.sql), which
-- are never changed. The owner runs this once, after the smoke test, with: sudo mysql gluttonyDB < schema-part2.sql
-- Milestone 1: accounts and the diet profile. Milestone 2: lists, Devoured, ratings and notes (below).

CREATE TABLE Users (
  UserID INT NOT NULL AUTO_INCREMENT,
  Username VARCHAR(32) NOT NULL,
  PasswordHash VARCHAR(255) NOT NULL,
  CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (UserID),
  UNIQUE KEY ux_users_username (Username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- A device that signs in by itself. Its last sign-in is read from its newest session, as in Pageturner.
CREATE TABLE Devices (
  Fingerprint VARCHAR(255) NOT NULL,
  UserID INT NOT NULL,
  PRIMARY KEY (Fingerprint),
  KEY ix_devices_user (UserID),
  CONSTRAINT fk_devices_user FOREIGN KEY (UserID) REFERENCES Users (UserID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE Sessions (
  Token CHAR(64) NOT NULL,
  UserID INT NOT NULL,
  DeviceFingerprint VARCHAR(255) NOT NULL,
  ExpiresAt DATETIME NOT NULL,
  PRIMARY KEY (Token),
  KEY ix_sessions_user (UserID),
  CONSTRAINT fk_sessions_user FOREIGN KEY (UserID) REFERENCES Users (UserID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- The owner inserts a row by hand for each friend: INSERT INTO LoginKeys (KeyValue) VALUES ('<a long random key>');
CREATE TABLE LoginKeys (
  KeyValue VARCHAR(64) NOT NULL,
  Used TINYINT(1) NOT NULL DEFAULT 0,
  UsedBy INT NULL,
  CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (KeyValue),
  CONSTRAINT fk_loginkeys_user FOREIGN KEY (UsedBy) REFERENCES Users (UserID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- The diet profile, in part 1's words (gluttonyRules.DIETS and CONTAINS_ITEMS).
CREATE TABLE UserDiets (
  UserID INT NOT NULL,
  Diet VARCHAR(20) NOT NULL,
  PRIMARY KEY (UserID, Diet),
  CONSTRAINT fk_userdiets_user FOREIGN KEY (UserID) REFERENCES Users (UserID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE UserAvoids (
  UserID INT NOT NULL,
  Item VARCHAR(20) NOT NULL,
  PRIMARY KEY (UserID, Item),
  CONSTRAINT fk_useravoids_user FOREIGN KEY (UserID) REFERENCES Users (UserID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- What each person keeps. Every row names its user, and the routes look every one up together with the
-- user's id, so someone else's id is simply not found. Rows reference Recipes with ON DELETE CASCADE, which never
-- fires in practice: part 1 only hides recipes (RemovedAt), and a hidden one stays visible to whoever kept it.

-- Each account has exactly one 'cravings' list, made at sign-up, which can't be renamed or deleted. CravingsOf is
-- the user's id on that list and NULL on every other (the sign-up sets it, and the CHECK keeps it in step with
-- Kind, which is always written in lowercase), so the unique key allows one Cravings per account and any number
-- of custom lists, even under a race. It is a plain column, not a generated one: MySQL refuses ON DELETE CASCADE
-- on a foreign key over the base column of a stored generated column. OrderIndex orders the custom lists
-- (Cravings always shows first).
CREATE TABLE Lists (
  ListID INT NOT NULL AUTO_INCREMENT,
  UserID INT NOT NULL,
  Title VARCHAR(60) NOT NULL,
  Kind VARCHAR(10) NOT NULL,
  OrderIndex INT NOT NULL DEFAULT 0,
  CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CravingsOf INT NULL,
  PRIMARY KEY (ListID),
  KEY ix_lists_user (UserID),
  UNIQUE KEY ux_lists_cravings (CravingsOf),
  CONSTRAINT ck_lists_kind CHECK (Kind IN ('cravings', 'custom')),
  CONSTRAINT ck_lists_cravingsof CHECK ((Kind = 'cravings') = (CravingsOf IS NOT NULL)),
  CONSTRAINT fk_lists_user FOREIGN KEY (UserID) REFERENCES Users (UserID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- A list reads in OrderIndex order, smallest first; a new item takes the smallest index minus one, so it is on top.
CREATE TABLE ListItems (
  ListID INT NOT NULL,
  RecipeID INT NOT NULL,
  OrderIndex INT NOT NULL,
  AddedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ListID, RecipeID),
  KEY ix_listitems_recipe (RecipeID),
  KEY ix_listitems_order (ListID, OrderIndex),
  CONSTRAINT fk_listitems_list FOREIGN KEY (ListID) REFERENCES Lists (ListID) ON DELETE CASCADE,
  CONSTRAINT fk_listitems_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- One row per time a person made the recipe. ClientID is made by the app, so a mark sent twice (a retry, or
-- milestone 3's offline queue) is stored once.
CREATE TABLE Devoured (
  DevouredID INT NOT NULL AUTO_INCREMENT,
  UserID INT NOT NULL,
  RecipeID INT NOT NULL,
  MadeOn DATE NOT NULL,
  ClientID CHAR(36) NOT NULL,
  CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (DevouredID),
  UNIQUE KEY ux_devoured_client (ClientID),
  KEY ix_devoured_user_made (UserID, MadeOn),
  KEY ix_devoured_recipe (RecipeID),
  CONSTRAINT fk_devoured_user FOREIGN KEY (UserID) REFERENCES Users (UserID) ON DELETE CASCADE,
  CONSTRAINT fk_devoured_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Stars and notes remember when they last changed, in UTC to the millisecond, written by the routes (never by
-- MySQL's clock, which follows the server's zone). A cleared rating stays as a row with Stars NULL and a deleted
-- note as a row with no text: /sync/batch compares a change queued offline with that moment, so a change made
-- before the clearing never brings the old value back.
CREATE TABLE Ratings (
  UserID INT NOT NULL,
  RecipeID INT NOT NULL,
  Stars TINYINT NULL,
  UpdatedAt DATETIME(3) NOT NULL,
  PRIMARY KEY (UserID, RecipeID),
  CONSTRAINT ck_ratings_stars CHECK (Stars IS NULL OR Stars BETWEEN 1 AND 5),
  CONSTRAINT fk_ratings_user FOREIGN KEY (UserID) REFERENCES Users (UserID) ON DELETE CASCADE,
  CONSTRAINT fk_ratings_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- A private note, up to 2,000 characters (utf8mb4 counts characters, as the routes do). Text '' is a deleted note.
CREATE TABLE Notes (
  UserID INT NOT NULL,
  RecipeID INT NOT NULL,
  Text VARCHAR(2000) NOT NULL,
  UpdatedAt DATETIME(3) NOT NULL,
  PRIMARY KEY (UserID, RecipeID),
  CONSTRAINT fk_notes_user FOREIGN KEY (UserID) REFERENCES Users (UserID) ON DELETE CASCADE,
  CONSTRAINT fk_notes_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
