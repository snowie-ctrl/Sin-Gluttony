-- Gluttony part 2: accounts and what each person keeps, beside part 1's catalog tables (schema.sql), which
-- are never changed. The owner runs this once, after the smoke test, with: sudo mysql gluttonyDB < schema-part2.sql
-- Milestone 1: accounts and the diet profile. Milestone 2 appends lists, Devoured, ratings and notes here.

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
