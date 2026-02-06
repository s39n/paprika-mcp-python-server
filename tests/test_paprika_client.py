from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paprika_mcp_server.paprika_client import PaprikaAPIError, PaprikaClient, ValidationError


class TestPaprikaClient:
    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    @pytest.mark.asyncio
    async def test_authentication_success(self, client):
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"result": {"token": "test_token"}}
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            token = await client.authenticate()
            assert token == "test_token"
            assert client.token == "test_token"

    @pytest.mark.asyncio
    async def test_authentication_failure(self, client):
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 401
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            with pytest.raises(PaprikaAPIError):
                await client.authenticate()


class TestInputValidation:
    """Tests for input validation (add-input-validation spec)"""

    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    # Recipe name validation tests
    def test_validate_recipe_name_empty(self, client):
        """Test that empty recipe name raises ValidationError"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            client._validate_recipe_name("")

    def test_validate_recipe_name_whitespace_only(self, client):
        """Test that whitespace-only recipe name raises ValidationError"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            client._validate_recipe_name("   ")

    def test_validate_recipe_name_none(self, client):
        """Test that None recipe name raises ValidationError"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            client._validate_recipe_name(None)

    def test_validate_recipe_name_too_long(self, client):
        """Test that recipe name over 200 chars raises ValidationError"""
        long_name = "a" * 201
        with pytest.raises(ValidationError, match="200 characters or less"):
            client._validate_recipe_name(long_name)

    def test_validate_recipe_name_valid(self, client):
        """Test that valid recipe name passes validation"""
        client._validate_recipe_name("Spaghetti Carbonara")  # Should not raise

    # Ingredients validation tests
    def test_validate_ingredients_empty_string(self, client):
        """Test that empty ingredients string raises ValidationError"""
        with pytest.raises(ValidationError, match="Ingredients"):
            client._validate_ingredients("")

    def test_validate_ingredients_empty_list(self, client):
        """Test that empty ingredients list raises ValidationError"""
        with pytest.raises(ValidationError, match="Ingredients"):
            client._validate_ingredients([])

    def test_validate_ingredients_none(self, client):
        """Test that None ingredients raises ValidationError"""
        with pytest.raises(ValidationError, match="Ingredients must be provided"):
            client._validate_ingredients(None)

    def test_validate_ingredients_list_with_empty_string(self, client):
        """Test that list with empty string raises ValidationError"""
        with pytest.raises(ValidationError, match="must be a non-empty string"):
            client._validate_ingredients(["400g pasta", "", "salt"])

    def test_validate_ingredients_valid_string(self, client):
        """Test that valid ingredients string passes validation"""
        client._validate_ingredients("400g spaghetti\n100g pancetta\nsalt")

    def test_validate_ingredients_valid_list(self, client):
        """Test that valid ingredients list passes validation"""
        client._validate_ingredients(["400g spaghetti", "100g pancetta", "salt"])

    # Directions validation tests
    def test_validate_directions_empty(self, client):
        """Test that empty directions raise ValidationError"""
        with pytest.raises(ValidationError, match="Recipe directions cannot be empty"):
            client._validate_directions("")

    def test_validate_directions_whitespace_only(self, client):
        """Test that whitespace-only directions raise ValidationError"""
        with pytest.raises(ValidationError, match="Recipe directions cannot be empty"):
            client._validate_directions("   \n  ")

    def test_validate_directions_valid(self, client):
        """Test that valid directions pass validation"""
        client._validate_directions("1. Cook pasta\n2. Fry pancetta\n3. Combine")

    # Numeric field validation tests
    def test_validate_numeric_field_negative(self, client):
        """Test that negative numeric value raises ValidationError"""
        with pytest.raises(ValidationError, match="cannot be negative"):
            client._validate_numeric_field(-1, "Servings", min_val=0)

    def test_validate_numeric_field_below_minimum(self, client):
        """Test that value below minimum raises ValidationError"""
        with pytest.raises(ValidationError, match="must be at least 1"):
            client._validate_numeric_field(0, "Servings", min_val=1)

    def test_validate_numeric_field_invalid_string(self, client):
        """Test that non-numeric string raises ValidationError"""
        with pytest.raises(ValidationError, match="must be a number"):
            client._validate_numeric_field("abc", "Servings")

    def test_validate_numeric_field_valid_int(self, client):
        """Test that valid integer passes validation"""
        client._validate_numeric_field(4, "Servings", min_val=1)

    def test_validate_numeric_field_valid_string_int(self, client):
        """Test that valid string integer passes validation"""
        client._validate_numeric_field("4", "Servings", min_val=1)

    def test_validate_numeric_field_empty_string(self, client):
        """Test that empty string is allowed for optional fields"""
        client._validate_numeric_field("", "Servings")  # Should not raise

    def test_validate_numeric_field_none(self, client):
        """Test that None is allowed for optional fields"""
        client._validate_numeric_field(None, "Servings")  # Should not raise

    # Integration tests with create_recipe
    @pytest.mark.asyncio
    async def test_create_recipe_validation_empty_name(self, client):
        """Test create_recipe with empty name fails validation"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            await client.create_recipe(
                name="",
                ingredients="400g pasta",
                directions="Cook pasta",
            )

    @pytest.mark.asyncio
    async def test_create_recipe_validation_empty_ingredients(self, client):
        """Test create_recipe with empty ingredients fails validation"""
        with pytest.raises(ValidationError, match="Ingredients"):
            await client.create_recipe(
                name="Pasta",
                ingredients="",
                directions="Cook pasta",
            )

    @pytest.mark.asyncio
    async def test_create_recipe_validation_empty_directions(self, client):
        """Test create_recipe with empty directions fails validation"""
        with pytest.raises(ValidationError, match="directions cannot be empty"):
            await client.create_recipe(
                name="Pasta",
                ingredients="400g pasta",
                directions="",
            )

    @pytest.mark.asyncio
    async def test_create_recipe_validation_invalid_servings(self, client):
        """Test create_recipe with invalid servings fails validation"""
        with pytest.raises(ValidationError, match="Servings"):
            await client.create_recipe(
                name="Pasta",
                ingredients="400g pasta",
                directions="Cook pasta",
                servings="-1",
            )

    # Integration tests with update_recipe_partial
    @pytest.mark.asyncio
    async def test_update_recipe_partial_validation_empty_uid(self, client):
        """Test update_recipe_partial with empty UID fails validation"""
        with pytest.raises(ValidationError, match="UID is required"):
            await client.update_recipe_partial(uid="", name="New Name")

    @pytest.mark.asyncio
    async def test_update_recipe_partial_validation_none_uid(self, client):
        """Test update_recipe_partial with None UID fails validation"""
        with pytest.raises(ValidationError, match="UID is required"):
            await client.update_recipe_partial(uid=None, name="New Name")

    @pytest.mark.asyncio
    async def test_update_recipe_partial_validation_invalid_name(self, client):
        """Test update_recipe_partial with invalid name fails validation"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            await client.update_recipe_partial(
                uid="TEST-UID-123",
                name="",
            )

    @pytest.mark.asyncio
    async def test_update_recipe_partial_validation_invalid_servings(self, client):
        """Test update_recipe_partial with invalid servings fails validation"""
        with pytest.raises(ValidationError, match="Servings"):
            await client.update_recipe_partial(
                uid="TEST-UID-123",
                servings="0",
            )
