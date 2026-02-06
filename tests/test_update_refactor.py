from unittest.mock import AsyncMock, patch

import pytest

from paprika_mcp_server.paprika_client import PaprikaClient


class TestUpdateRecipeRefactor:
    """Tests for consolidated update_recipe functionality"""

    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    @pytest.fixture
    def existing_recipe(self):
        """Sample existing recipe for update tests"""
        return {
            "uid": "TEST-UID-123",
            "name": "Original Recipe",
            "ingredients": "Original ingredients",
            "directions": "Original directions",
            "description": "Original description",
            "notes": "Original notes",
            "servings": "4",
            "prep_time": "10 mins",
            "cook_time": "20 mins",
            "difficulty": "Easy",
            "created": "2024-01-01 10:00:00",
            "in_trash": False,
        }

    @pytest.mark.asyncio
    async def test_update_recipe_partial_single_field(self, client, existing_recipe):
        """Test updating only one field (name)"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            # Mock GET request to fetch existing recipe
            mock_request.side_effect = [
                {"result": existing_recipe},  # GET existing recipe
                {"result": {"status": "ok"}},  # POST update
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-123",
                name="New Recipe Name",
            )

            assert result["name"] == "New Recipe Name"
            # Other fields should remain unchanged
            assert result["ingredients"] == "Original ingredients"
            assert result["directions"] == "Original directions"
            assert result["servings"] == "4"

    @pytest.mark.asyncio
    async def test_update_recipe_partial_multiple_fields(self, client, existing_recipe):
        """Test updating multiple fields"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": existing_recipe},
                {"result": {"status": "ok"}},
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-123",
                name="New Name",
                servings="6",
                prep_time="15 mins",
            )

            assert result["name"] == "New Name"
            assert result["servings"] == "6"
            assert result["prep_time"] == "15 mins"
            # Unchanged fields
            assert result["ingredients"] == "Original ingredients"
            assert result["directions"] == "Original directions"

    @pytest.mark.asyncio
    async def test_update_recipe_partial_all_fields(self, client, existing_recipe):
        """Test full recipe update using partial method (backward compat)"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": existing_recipe},
                {"result": {"status": "ok"}},
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-123",
                name="Completely New Recipe",
                ingredients="New ingredients",
                directions="New directions",
                description="New description",
                notes="New notes",
                servings="8",
                prep_time="30 mins",
                cook_time="60 mins",
                difficulty="Hard",
            )

            assert result["name"] == "Completely New Recipe"
            assert result["ingredients"] == "New ingredients"
            assert result["directions"] == "New directions"
            assert result["servings"] == "8"
            assert result["difficulty"] == "Hard"

    @pytest.mark.asyncio
    async def test_update_recipe_partial_empty_values_ignored(self, client, existing_recipe):
        """Test that empty string values don't overwrite existing data"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": existing_recipe},
                {"result": {"status": "ok"}},
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-123",
                name="New Name",
                servings="",  # Empty string should be ignored
            )

            assert result["name"] == "New Name"
            # Empty servings should not overwrite
            assert result["servings"] == "4"  # Original value preserved

    @pytest.mark.asyncio
    async def test_update_recipe_partial_none_values_ignored(self, client, existing_recipe):
        """Test that None values don't overwrite existing data"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": existing_recipe},
                {"result": {"status": "ok"}},
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-123",
                name="New Name",
                notes=None,  # None should be ignored
            )

            assert result["name"] == "New Name"
            assert result["notes"] == "Original notes"  # Original value preserved

    @pytest.mark.asyncio
    async def test_update_recipe_partial_updates_timestamp(self, client, existing_recipe):
        """Test that update recalculates timestamp and hash"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": existing_recipe},
                {"result": {"status": "ok"}},
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-123",
                name="New Name",
            )

            # Timestamp should be updated
            assert result["created"] != "2024-01-01 10:00:00"
            # Hash should be recalculated
            assert "hash" in result

    @pytest.mark.asyncio
    async def test_update_recipe_partial_recipe_not_found(self, client):
        """Test update_recipe_partial with non-existent recipe"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {"result": {}}  # Empty result = not found

            with pytest.raises(Exception, match="not found"):
                await client.update_recipe_partial(
                    uid="NONEXISTENT-UID",
                    name="New Name",
                )

    @pytest.mark.asyncio
    async def test_update_recipe_only_uid_required(self, client, existing_recipe):
        """Test that only UID is required, all other fields optional"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": existing_recipe},
                {"result": {"status": "ok"}},
            ]

            # Should work with just UID (no changes, but valid)
            result = await client.update_recipe_partial(uid="TEST-UID-123")

            # Recipe should be returned unchanged (except timestamp/hash)
            assert result["name"] == "Original Recipe"
            assert result["ingredients"] == "Original ingredients"


class TestUpdateRecipeFlexibility:
    """Tests demonstrating the flexibility of the unified update_recipe"""

    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    @pytest.fixture
    def sample_recipe(self):
        return {
            "uid": "TEST-UID-456",
            "name": "Pasta Carbonara",
            "ingredients": "400g spaghetti\n100g pancetta\n2 eggs",
            "directions": "1. Cook pasta\n2. Fry pancetta\n3. Mix with eggs",
            "description": "Classic Italian",
            "notes": "",
            "servings": "4",
            "prep_time": "10 mins",
            "cook_time": "15 mins",
            "difficulty": "Medium",
            "created": "2024-01-01 10:00:00",
            "in_trash": False,
        }

    @pytest.mark.asyncio
    async def test_just_change_prep_time(self, client, sample_recipe):
        """Test changing only prep time (common use case)"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": sample_recipe},
                {"result": {"status": "ok"}},
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-456",
                prep_time="5 mins",
            )

            assert result["prep_time"] == "5 mins"
            assert result["cook_time"] == "15 mins"  # Unchanged

    @pytest.mark.asyncio
    async def test_add_notes_to_recipe(self, client, sample_recipe):
        """Test adding notes to a recipe without notes"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": sample_recipe},
                {"result": {"status": "ok"}},
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-456",
                notes="Use room temperature eggs to prevent scrambling",
            )

            assert "room temperature" in result["notes"]
            assert result["name"] == "Pasta Carbonara"  # Unchanged

    @pytest.mark.asyncio
    async def test_adjust_servings(self, client, sample_recipe):
        """Test adjusting servings (common use case)"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": sample_recipe},
                {"result": {"status": "ok"}},
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-456",
                servings="6",
            )

            assert result["servings"] == "6"

    @pytest.mark.asyncio
    async def test_change_difficulty_level(self, client, sample_recipe):
        """Test changing difficulty level"""
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": sample_recipe},
                {"result": {"status": "ok"}},
            ]

            result = await client.update_recipe_partial(
                uid="TEST-UID-456",
                difficulty="Easy",
            )

            assert result["difficulty"] == "Easy"
            assert result["name"] == "Pasta Carbonara"  # Unchanged


class TestUpdateRecipeBackwardCompatibility:
    """Tests ensuring backward compatibility with old update patterns"""

    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    @pytest.mark.asyncio
    async def test_old_full_update_pattern_still_works(self, client):
        """Test that old 'full update' pattern works with new unified method"""
        existing = {
            "uid": "TEST-UID-789",
            "name": "Old Name",
            "ingredients": "Old ingredients",
            "directions": "Old directions",
            "description": "",
            "notes": "",
            "servings": "2",
            "prep_time": "",
            "cook_time": "",
            "difficulty": "",
            "created": "2024-01-01 10:00:00",
            "in_trash": False,
        }

        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": existing},
                {"result": {"status": "ok"}},
            ]

            # Old pattern: provide all fields
            result = await client.update_recipe_partial(
                uid="TEST-UID-789",
                name="New Name",
                ingredients="New ingredients",
                directions="New directions",
                description="New description",
                notes="New notes",
                servings="4",
                prep_time="10 mins",
                cook_time="20 mins",
                difficulty="Medium",
            )

            assert result["name"] == "New Name"
            assert result["ingredients"] == "New ingredients"
            assert result["servings"] == "4"

    @pytest.mark.asyncio
    async def test_old_partial_update_pattern_still_works(self, client):
        """Test that old 'partial update' pattern still works"""
        existing = {
            "uid": "TEST-UID-101",
            "name": "Recipe Name",
            "ingredients": "Ingredients",
            "directions": "Directions",
            "description": "Description",
            "notes": "Notes",
            "servings": "4",
            "prep_time": "10 mins",
            "cook_time": "20 mins",
            "difficulty": "Easy",
            "created": "2024-01-01 10:00:00",
            "in_trash": False,
        }

        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.side_effect = [
                {"result": existing},
                {"result": {"status": "ok"}},
            ]

            # Old partial pattern: provide only changed fields
            result = await client.update_recipe_partial(
                uid="TEST-UID-101",
                servings="6",
            )

            assert result["servings"] == "6"
            assert result["name"] == "Recipe Name"  # Unchanged
