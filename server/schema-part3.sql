-- Gluttony part 3, milestone 2: pairings (what goes with a recipe).
-- The owner runs this once with `sudo mysql gluttonyDB < schema-part3.sql`, after schema.sql, schema-part2.sql and
-- schema-catalog.sql. It adds one table and touches no other.

-- A recipe's suggestions, per slot (side, sauce, dessert, drink, goes-on, snack) in rank order (Position, from 1;
-- RANK is a reserved word in MySQL 8). The scraper replaces a recipe's whole set each time it changes. Why is the
-- reason in plain words. Both recipes reference Recipes, so a pairing goes when either recipe does; a removed or
-- hidden recipe stays a row here and is left out when the recipe page reads its pairings.
CREATE TABLE RecipePairings (
  RecipeID INT NOT NULL,
  Slot VARCHAR(10) NOT NULL,
  Position TINYINT NOT NULL,
  PairedID INT NOT NULL,
  Why VARCHAR(120) NOT NULL,
  PRIMARY KEY (RecipeID, Slot, Position),
  KEY ix_pairings_paired (PairedID),
  CONSTRAINT fk_pairings_recipe FOREIGN KEY (RecipeID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE,
  CONSTRAINT fk_pairings_paired FOREIGN KEY (PairedID) REFERENCES Recipes (RecipeID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
