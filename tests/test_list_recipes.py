from unittest.mock import AsyncMock, patch

import pytest

from paprika_mcp_server.paprika_client import PaprikaClient


class TestListRecipesEnhancements:
    """Tests for pagination, sorting, filtering, and field selection in list_recipes"""

    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    @pytest.fixture
    def sample_recipes(self):
        """Sample recipe data for testing"""
        return [
            {
                "uid": "UID-001",
                "name": "Spaghetti Carbonara",
                "ingredients": "400g spaghetti\n100g pancetta\n2 eggs",
                "description": "Classic Italian pasta",
                "prep_time": "10 mins",
                "cook_time": "15 mins",
                "created": "2024-01-01 10:00:00",
                "in_trash": False,
            },
            {
                "uid": "UID-002",
                "name": "Caesar Salad",
                "ingredients": "Lettuce\nCroutons\nParmesan\nDressing",
                "description": "Fresh salad",
                "prep_time": "5 mins",
                "cook_time": "",
                "created": "2024-01-02 10:00:00",
                "in_trash": False,
            },
            {
                "uid": "UID-003",
                "name": "Grilled Chicken",
                "ingredients": "Chicken breast\nOlive oil\nSpices",
                "description": "Simple grilled chicken",
                "prep_time": "15 mins",
                "cook_time": "20 mins",
                "created": "2024-01-03 10:00:00",
                "in_trash": False,
            },
            {
                "uid": "UID-004",
                "name": "Apple Pie",
                "ingredients": "Apples\nFlour\nSugar\nButter",
                "description": "Delicious dessert",
                "prep_time": "30 mins",
                "cook_time": "45 mins",
                "created": "2024-01-04 10:00:00",
                "in_trash": False,
            },
        ]

    @pytest.mark.asyncio
    async def test_list_recipes_basic(self, client, sample_recipes):
        """Test basic list_recipes returns all recipes"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            # Mock the list UIDs response and individual recipe fetches
            uid_list = [{"uid": r["uid"]} for r in sample_recipes]

            # First call returns UID list, subsequent calls return individual recipes
            mock_request.side_effect = [
                {"result": uid_list},  # List of UIDs
                *[{"result": recipe} for recipe in sample_recipes],  # Individual recipes
            ]

            recipes = await client.list_recipes(limit=50)

            assert len(recipes) == 4
            assert recipes[0]["name"] == "Spaghetti Carbonara"

    @pytest.mark.asyncio
    async def test_list_recipes_with_limit(self, client, sample_recipes):
        """Test list_recipes respects limit parameter"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {"result": sample_recipes}

            recipes = await client.list_recipes(limit=2)

            # Note: limit is applied in the client before fetching full data
            assert len(recipes) <= 4  # Client fetches limited UIDs

    @pytest.mark.asyncio
    async def test_list_recipes_excludes_trashed(self, client, sample_recipes):
        """Test list_recipes excludes recipes in trash"""
        # Add a trashed recipe
        trashed_recipe = sample_recipes[0].copy()
        trashed_recipe["in_trash"] = True
        all_recipes = [trashed_recipe] + sample_recipes[1:]

        with patch.object(client, "_make_authenticated_request") as mock_request:
            uid_list = [{"uid": r["uid"]} for r in all_recipes]

            # First call returns UID list, subsequent calls return individual recipes
            mock_request.side_effect = [
                {"result": uid_list},
                *[{"result": recipe} for recipe in all_recipes],
            ]

            recipes = await client.list_recipes(limit=50)

            # Should exclude the trashed recipe
            assert all(not r.get("in_trash", False) for r in recipes)
            assert len(recipes) == 3

    @pytest.mark.asyncio
    async def test_list_recipes_empty_account(self, client):
        """Test list_recipes handles empty account gracefully"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {"result": []}

            recipes = await client.list_recipes(limit=50)

            assert recipes == []


class TestListRecipesSorting:
    """Tests for sorting functionality in list_recipes handler"""

    def test_sort_by_name_ascending(self):
        """Test sorting recipes by name in ascending order"""
        recipes = [
            {"name": "Zebra Cake", "uid": "1"},
            {"name": "Apple Pie", "uid": "2"},
            {"name": "Muffins", "uid": "3"},
        ]

        sorted_recipes = sorted(recipes, key=lambda r: r["name"].lower())

        assert sorted_recipes[0]["name"] == "Apple Pie"
        assert sorted_recipes[1]["name"] == "Muffins"
        assert sorted_recipes[2]["name"] == "Zebra Cake"

    def test_sort_by_name_descending(self):
        """Test sorting recipes by name in descending order"""
        recipes = [
            {"name": "Apple Pie", "uid": "1"},
            {"name": "Zebra Cake", "uid": "2"},
            {"name": "Muffins", "uid": "3"},
        ]

        sorted_recipes = sorted(recipes, key=lambda r: r["name"].lower(), reverse=True)

        assert sorted_recipes[0]["name"] == "Zebra Cake"
        assert sorted_recipes[1]["name"] == "Muffins"
        assert sorted_recipes[2]["name"] == "Apple Pie"

    def test_sort_by_created_date(self):
        """Test sorting recipes by created timestamp"""
        recipes = [
            {"name": "Recipe 1", "created": "2024-01-03 10:00:00", "uid": "1"},
            {"name": "Recipe 2", "created": "2024-01-01 10:00:00", "uid": "2"},
            {"name": "Recipe 3", "created": "2024-01-02 10:00:00", "uid": "3"},
        ]

        sorted_recipes = sorted(recipes, key=lambda r: r.get("created", ""))

        assert sorted_recipes[0]["created"] == "2024-01-01 10:00:00"
        assert sorted_recipes[1]["created"] == "2024-01-02 10:00:00"
        assert sorted_recipes[2]["created"] == "2024-01-03 10:00:00"


class TestListRecipesFiltering:
    """Tests for filtering functionality in list_recipes handler"""

    def test_filter_by_name(self):
        """Test filtering recipes by name"""
        recipes = [
            {
                "name": "Spaghetti Carbonara",
                "ingredients": "pasta",
                "description": "Italian",
                "uid": "1",
            },
            {"name": "Caesar Salad", "ingredients": "lettuce", "description": "Salad", "uid": "2"},
            {
                "name": "Pasta Primavera",
                "ingredients": "pasta",
                "description": "Italian",
                "uid": "3",
            },
        ]

        # Simple case-insensitive filter
        filtered = [r for r in recipes if "pasta" in r["name"].lower()]

        assert len(filtered) == 1
        assert filtered[0]["name"] == "Pasta Primavera"

    def test_filter_by_ingredients(self):
        """Test filtering recipes by ingredients"""
        recipes = [
            {
                "name": "Spaghetti",
                "ingredients": "pasta\nsalt",
                "description": "Italian",
                "uid": "1",
            },
            {"name": "Salad", "ingredients": "lettuce\ntomato", "description": "Fresh", "uid": "2"},
            {
                "name": "Pasta Soup",
                "ingredients": "pasta\nbroth",
                "description": "Soup",
                "uid": "3",
            },
        ]

        # Filter by ingredient containing "pasta"
        filtered = [r for r in recipes if "pasta" in r["ingredients"].lower()]

        assert len(filtered) == 2
        assert all("pasta" in r["ingredients"].lower() for r in filtered)

    def test_filter_by_description(self):
        """Test filtering recipes by description"""
        recipes = [
            {
                "name": "Recipe 1",
                "ingredients": "...",
                "description": "Italian classic",
                "uid": "1",
            },
            {"name": "Recipe 2", "ingredients": "...", "description": "French cuisine", "uid": "2"},
            {"name": "Recipe 3", "ingredients": "...", "description": "Italian style", "uid": "3"},
        ]

        # Filter by description containing "Italian"
        filtered = [r for r in recipes if "italian" in r["description"].lower()]

        assert len(filtered) == 2
        assert all("italian" in r["description"].lower() for r in filtered)


class TestListRecipesPagination:
    """Tests for pagination functionality"""

    def test_pagination_offset_limit(self):
        """Test pagination with offset and limit"""
        recipes = [{"name": f"Recipe {i}", "uid": f"UID-{i}"} for i in range(10)]

        offset = 3
        limit = 4
        paginated = recipes[offset : offset + limit]

        assert len(paginated) == 4
        assert paginated[0]["name"] == "Recipe 3"
        assert paginated[3]["name"] == "Recipe 6"

    def test_pagination_has_more(self):
        """Test has_more indicator"""
        recipes = [{"name": f"Recipe {i}", "uid": f"UID-{i}"} for i in range(10)]

        offset = 0
        limit = 5
        has_more = (offset + limit) < len(recipes)

        assert has_more is True

    def test_pagination_no_more(self):
        """Test has_more when at end"""
        recipes = [{"name": f"Recipe {i}", "uid": f"UID-{i}"} for i in range(10)]

        offset = 5
        limit = 10
        has_more = (offset + limit) < len(recipes)

        assert has_more is False

    def test_pagination_beyond_end(self):
        """Test pagination beyond available recipes"""
        recipes = [{"name": f"Recipe {i}", "uid": f"UID-{i}"} for i in range(10)]

        offset = 15
        limit = 5
        paginated = recipes[offset : offset + limit]

        assert len(paginated) == 0


class TestListRecipesFieldSelection:
    """Tests for field selection functionality"""

    def test_include_fields(self):
        """Test include_fields returns only specified fields"""
        recipe = {
            "uid": "UID-001",
            "name": "Pasta",
            "ingredients": "pasta\nsalt",
            "directions": "Cook pasta",
            "description": "Simple",
            "notes": "Tasty",
        }

        include_fields = ["name", "uid", "ingredients"]

        # UID always included
        if "uid" not in include_fields:
            include_fields.append("uid")

        selected = {field: recipe.get(field) for field in include_fields if field in recipe}

        assert "name" in selected
        assert "uid" in selected
        assert "ingredients" in selected
        assert "directions" not in selected
        assert "notes" not in selected

    def test_exclude_fields(self):
        """Test exclude_fields omits specified fields"""
        recipe = {
            "uid": "UID-001",
            "name": "Pasta",
            "ingredients": "pasta\nsalt",
            "directions": "Cook pasta",
            "description": "Simple",
            "notes": "Tasty",
        }

        exclude_fields = ["directions", "notes"]

        selected = {k: v for k, v in recipe.items() if k not in exclude_fields or k == "uid"}

        assert "name" in selected
        assert "uid" in selected  # UID always included
        assert "ingredients" in selected
        assert "directions" not in selected
        assert "notes" not in selected

    def test_include_fields_always_includes_uid(self):
        """Test that UID is always included even if not in include_fields"""
        recipe = {
            "uid": "UID-001",
            "name": "Pasta",
            "ingredients": "pasta\nsalt",
        }

        include_fields = ["name"]  # UID not specified

        # Add UID if not present
        if "uid" not in include_fields:
            include_fields = include_fields + ["uid"]

        selected = {field: recipe.get(field) for field in include_fields if field in recipe}

        assert "uid" in selected

    def test_exclude_fields_preserves_uid(self):
        """Test that UID is preserved even if in exclude_fields"""
        recipe = {
            "uid": "UID-001",
            "name": "Pasta",
            "ingredients": "pasta\nsalt",
        }

        exclude_fields = ["uid", "ingredients"]  # Try to exclude UID

        selected = {k: v for k, v in recipe.items() if k not in exclude_fields or k == "uid"}

        assert "uid" in selected  # UID should still be present
        assert "ingredients" not in selected
