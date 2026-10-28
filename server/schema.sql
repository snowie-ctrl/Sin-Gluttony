-- gluttonyDB: Gluttony's recipe catalog. Run once by the owner:
--   sudo mysql -e "CREATE DATABASE gluttonyDB CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
--   sudo mysql gluttonyDB < schema.sql
-- Multi-valued facts live in child tables (no SET, ENUM or JSON columns), as in pageturnerDB.

CREATE TABLE Ingredients (
  IngredientID INT NOT NULL AUTO_INCREMENT,
  Name VARCHAR(120) NOT NULL,
  ParentID INT NULL,
  Category VARCHAR(40) NULL,
  Origin VARCHAR(10) NOT NULL,
  AddedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (IngredientID),
  UNIQUE KEY uq_ingredients_name (Name),
  KEY ix_ingredients_parent (ParentID),
  CONSTRAINT fk_ingredients_parent FOREIGN KEY (ParentID) REFERENCES Ingredients (IngredientID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IngredientContains (
  IngredientID INT NOT NULL,
  Item VARCHAR(20) NOT NULL,
  PRIMARY KEY (IngredientID, Item),
  CONSTRAINT fk_contains_ingredient FOREIGN KEY (IngredientID) REFERENCES Ingredients (IngredientID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IngredientAliases (
  Alias VARCHAR(160) NOT NULL,
  IngredientID INT NOT NULL,
  Origin VARCHAR(10) NOT NULL,
  PRIMARY KEY (Alias),
  KEY ix_aliases_ingredient (IngredientID),
  CONSTRAINT fk_aliases_ingredient FOREIGN KEY (IngredientID) REFERENCES Ingredients (IngredientID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE Recipes (
  RecipeID INT NOT NULL AUTO_INCREMENT,
  Source VARCHAR(20) NOT NULL,
  SourceID VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  Kind VARCHAR(10) NOT NULL,
  Title VARCHAR(255) NOT NULL,
  DishKey VARCHAR(255) NOT NULL,
  Course VARCHAR(20) NULL,
  Cuisine VARCHAR(40) NULL,
  Servings SMALLINT NULL,
  ServingsFrom VARCHAR(10) NULL,
  PrepMinutes SMALLINT NULL,
  CookMinutes SMALLINT NULL,
  TotalMinutes SMALLINT NULL,
  TimeFrom VARCHAR(10) NULL,
  Difficulty TINYINT NULL,
  DifficultyFrom VARCHAR(10) NULL,
  Alcohol VARCHAR(15) NULL,
  Glass VARCHAR(60) NULL,
  ImagePath VARCHAR(40) NULL,
  ImageCredit VARCHAR(500) NULL,
  VideoUrl VARCHAR(500) NULL,
  SourceUrl VARCHAR(500) NULL,
  Licence VARCHAR(60) NOT NULL,
  Credit VARCHAR(500) NOT NULL,
  SearchText TEXT NOT NULL,
  ContentHash CHAR(40) NOT NULL,
  FirstSeen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  RemovedAt DATETIME NULL,
  PRIMARY KEY (RecipeID),
  UNIQUE KEY uq_recipes_source (Source, SourceID),
  KEY ix_recipes_dish (DishKey),
  KEY ix_recipes_course (Course),
  KEY ix_recipes_cuisine (Cuisine),
  KEY ix_recipes_minutes (TotalMinutes),
  FULLTEXT KEY ft_recipes_search (SearchText)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE RecipeIngredients (
  RecipeID INT NOT NULL,
  Position SMALLINT NOT NULL,
  Line VARCHAR(500) NOT NULL,
  Quantity DECIMAL(9,3) NULL,
  QuantityMax DECIMAL(9,3) NULL,
  Unit VARCHAR(20) NULL,
  IngredientID INT NULL,
  UnknownName VARCHAR(160) NULL,
  Note VARCHAR(255) NULL,
  Optional TINYINT(1) NOT NULL DEFAULT 0,
  GroupHeading VARCHAR(120) NULL,
  PRIMARY KEY (RecipeID, Position),
  KEY ix_ri_ingredient (IngredientID),
  KEY ix_ri_unknown (UnknownName),
  CONSTRAINT fk_ri_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE,
  CONSTRAINT fk_ri_ingredient FOREIGN KEY (IngredientID) REFERENCES Ingredients (IngredientID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE RecipeSteps (
  RecipeID INT NOT NULL,
  Position SMALLINT NOT NULL,
  Text TEXT NOT NULL,
  GroupHeading VARCHAR(120) NULL,
  PRIMARY KEY (RecipeID, Position),
  CONSTRAINT fk_steps_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE RecipeFacts (
  RecipeID INT NOT NULL,
  Complete TINYINT(1) NOT NULL,
  PRIMARY KEY (RecipeID),
  CONSTRAINT fk_facts_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE RecipeContains (
  RecipeID INT NOT NULL,
  Item VARCHAR(20) NOT NULL,
  PRIMARY KEY (RecipeID, Item),
  KEY ix_rc_item (Item),
  CONSTRAINT fk_rc_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE RecipeDiets (
  RecipeID INT NOT NULL,
  Diet VARCHAR(20) NOT NULL,
  PRIMARY KEY (RecipeID, Diet),
  KEY ix_rd_diet (Diet),
  CONSTRAINT fk_rd_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE RecipeTags (
  RecipeID INT NOT NULL,
  Type VARCHAR(10) NOT NULL,
  Tag VARCHAR(40) NOT NULL,
  Origin VARCHAR(10) NOT NULL,
  PRIMARY KEY (RecipeID, Type, Tag),
  KEY ix_rt_tag (Type, Tag),
  CONSTRAINT fk_rt_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
