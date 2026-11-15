-- Gluttony's new catalog (milestone 3): the recipe-site columns, nutrition, and the FDC food link.
-- The owner runs this once with `sudo mysql gluttonyDB < schema-catalog.sql`, after schema.sql and
-- schema-part2.sql. M4 runs it before the switch. It touches no user table.

-- Recipes: a short description, the gate's verdict (HiddenReason: the gate's first failing check;
-- NULL means listed) and the picture's width in pixels.
ALTER TABLE Recipes
  ADD COLUMN Description TEXT NULL AFTER Title,
  ADD COLUMN HiddenReason VARCHAR(20) NULL AFTER RemovedAt,
  ADD COLUMN ImageWidth INT NULL AFTER ImagePath,
  ADD KEY ix_recipes_hidden (HiddenReason);

-- Per-serving nutrition, one row per recipe; it goes with the recipe. NutritionFrom says whether the
-- figures came from the page (source) or were estimated; Flagged marks an estimate worth a second look.
CREATE TABLE RecipeNutrition (
  RecipeID INT NOT NULL,
  Calories DECIMAL(9,2) NULL, ProteinG DECIMAL(9,2) NULL, CarbsG DECIMAL(9,2) NULL, FatG DECIMAL(9,2) NULL,
  SatFatG DECIMAL(9,2) NULL, FibreG DECIMAL(9,2) NULL, SugarG DECIMAL(9,2) NULL, SodiumMg DECIMAL(9,2) NULL,
  NutritionFrom VARCHAR(10) NOT NULL,
  Flagged TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (RecipeID),
  CONSTRAINT fk_nutrition_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Ingredients: the USDA FDC food an ingredient is measured by, and who chose it (owner, curated or rule),
-- so a pass never overwrites the owner's pick. An owner's "no food fits" is FdcID NULL with FdcFrom owner.
ALTER TABLE Ingredients
  ADD COLUMN FdcID INT NULL AFTER Category,
  ADD COLUMN FdcFrom VARCHAR(10) NULL AFTER FdcID;
