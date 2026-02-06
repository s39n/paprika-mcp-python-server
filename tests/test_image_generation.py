import hashlib
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from io import BytesIO

from paprika_mcp_server.image_generator import ImageGenerator
from paprika_mcp_server.paprika_client import PaprikaClient


class TestImageGenerator:
    """Tests for the ImageGenerator class."""

    @pytest.fixture
    def image_generator(self):
        """Create an ImageGenerator instance for testing."""
        return ImageGenerator(api_token="test_token")

    @pytest.mark.asyncio
    async def test_generate_food_image_success(self, image_generator):
        """Test successful image generation."""
        mock_output = Mock()
        mock_output.url = "https://example.com/generated-image.png"

        with patch.object(image_generator, "_run_replicate_sync", return_value=mock_output):
            result = await image_generator.generate_food_image("Spaghetti Carbonara")

        assert result == "https://example.com/generated-image.png"

    @pytest.mark.asyncio
    async def test_generate_food_image_with_list_output(self, image_generator):
        """Test image generation with list output (multiple images)."""
        mock_output_item = Mock()
        mock_output_item.url = "https://example.com/generated-image.png"

        with patch.object(image_generator, "_run_replicate_sync", return_value=[mock_output_item]):
            result = await image_generator.generate_food_image("Thai Curry")

        assert result == "https://example.com/generated-image.png"

    @pytest.mark.asyncio
    async def test_generate_food_image_empty_name(self, image_generator):
        """Test that empty recipe names return None."""
        result = await image_generator.generate_food_image("")
        assert result is None

        result = await image_generator.generate_food_image("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_custom_food_image(self, image_generator):
        """Test custom image generation with styling instructions."""
        mock_output = Mock()
        mock_output.url = "https://example.com/custom-image.png"

        with patch.object(
            image_generator, "_run_replicate_sync", return_value=mock_output
        ) as mock_run:
            result = await image_generator.generate_custom_food_image(
                "Pasta Carbonara", "rustic style, darker lighting"
            )

        assert result == "https://example.com/custom-image.png"
        # Verify custom instructions were included in prompt
        call_args = mock_run.call_args[0][0]
        assert "rustic style" in call_args
        assert "darker lighting" in call_args

    @pytest.mark.asyncio
    async def test_generate_image_timeout(self, image_generator):
        """Test that image generation respects timeout and returns None on failure."""
        import time

        def slow_sync_operation(*args):
            # Synchronous sleep to simulate slow operation
            time.sleep(10)
            return Mock(url="https://example.com/image.png")

        image_generator.timeout = 0.1  # Very short timeout

        with patch.object(image_generator, "_run_replicate_sync", side_effect=slow_sync_operation):
            # generate_food_image catches timeout and returns None
            result = await image_generator.generate_food_image("Slow Recipe")
            assert result is None


class TestPaprikaImageOperations:
    """Tests for Paprika client image operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a PaprikaClient with mocked authentication."""
        client = PaprikaClient("test@example.com", "password")
        client.token = "test_token"
        return client

    @pytest.fixture
    def sample_image_bytes(self):
        """Generate sample image bytes for testing."""
        # Create a simple PNG header (minimal valid PNG)
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    @pytest.mark.asyncio
    async def test_download_image_success(self, mock_client, sample_image_bytes):
        """Test successful image download."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=sample_image_bytes)

        # Create async context manager mock for session.get()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_context)

        with patch.object(mock_client, "_get_session", return_value=mock_session):
            result = await mock_client._download_image("https://example.com/image.png")

        assert result is not None
        image_bytes, photo_hash = result
        assert image_bytes == sample_image_bytes
        assert len(photo_hash) == 64  # SHA256 hash length
        assert photo_hash.isupper()  # Hash should be uppercase

    @pytest.mark.asyncio
    async def test_download_image_hash_calculation(self, mock_client, sample_image_bytes):
        """Test that photo hash is calculated correctly."""
        expected_hash = hashlib.sha256(sample_image_bytes).hexdigest().upper()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=sample_image_bytes)

        # Create async context manager mock for session.get()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_context)

        with patch.object(mock_client, "_get_session", return_value=mock_session):
            result = await mock_client._download_image("https://example.com/image.png")

        _, photo_hash = result
        assert photo_hash == expected_hash

    @pytest.mark.asyncio
    async def test_download_image_failure(self, mock_client):
        """Test image download failure handling."""
        mock_response = AsyncMock()
        mock_response.status = 404

        # Create async context manager mock for session.get()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_context)

        with patch.object(mock_client, "_get_session", return_value=mock_session):
            result = await mock_client._download_image("https://example.com/not-found.png")

        assert result is None

    @pytest.mark.asyncio
    async def test_prepare_image_for_recipe(self, mock_client, sample_image_bytes):
        """Test preparing image metadata for recipe."""
        recipe = {
            "uid": "TEST-UID",
            "name": "Test Recipe",
            "photo": "",
            "photo_hash": "",
            "photo_large": None,
            "photo_url": None,
            "image_url": "",
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=sample_image_bytes)

        # Create async context manager mock for session.get()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_context)

        with patch.object(mock_client, "_get_session", return_value=mock_session):
            result = await mock_client._prepare_image_for_recipe(
                recipe, "https://example.com/image.png"
            )

        assert result is not None
        image_bytes, photo_filename = result

        # Verify image bytes
        assert image_bytes == sample_image_bytes

        # Verify filename format (UUID.png)
        assert photo_filename.endswith(".png")
        assert len(photo_filename) == 40  # UUID (36) + .png (4)

        # Verify recipe metadata was updated
        assert recipe["photo"] == photo_filename
        assert recipe["photo_large"] == photo_filename
        assert len(recipe["photo_hash"]) == 64
        assert recipe["photo_hash"].isupper()
        assert recipe["photo_url"] is None
        assert recipe["image_url"] is None

    @pytest.mark.asyncio
    async def test_create_recipe_with_image(self, mock_client, sample_image_bytes):
        """Test creating a recipe with AI-generated image."""
        # Mock image generator
        mock_image_gen = AsyncMock()
        mock_image_gen.generate_food_image = AsyncMock(
            return_value="https://example.com/generated.png"
        )
        mock_client.image_generator = mock_image_gen

        # Mock image download
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=sample_image_bytes)

        # Create async context manager mock for session.get()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_context)
        mock_session.post = AsyncMock()
        mock_session.request = AsyncMock()

        with patch.object(mock_client, "_get_session", return_value=mock_session):
            # Mock the API request
            with patch.object(
                mock_client, "_make_authenticated_request", new_callable=AsyncMock
            ) as mock_request:
                # Mock recipe_title_exists to return None (no duplicate)
                with patch.object(
                    mock_client, "recipe_title_exists", new_callable=AsyncMock, return_value=None
                ):
                    result = await mock_client.create_recipe(
                        name="Test Recipe",
                        ingredients="Test ingredients",
                        directions="Test directions",
                        generate_image=True,
                    )

        # Verify image generator was called
        mock_image_gen.generate_food_image.assert_called_once_with("Test Recipe", "")

        # Verify recipe was created with photo metadata
        assert result["photo"].endswith(".png")
        assert len(result["photo_hash"]) == 64
        assert result["photo_large"] is not None

    @pytest.mark.asyncio
    async def test_create_recipe_without_image(self, mock_client):
        """Test creating a recipe without image generation."""
        mock_session = AsyncMock()

        with patch.object(mock_client, "_get_session", return_value=mock_session):
            with patch.object(mock_client, "_make_authenticated_request", new_callable=AsyncMock):
                # Mock recipe_title_exists to return None (no duplicate)
                with patch.object(
                    mock_client, "recipe_title_exists", new_callable=AsyncMock, return_value=None
                ):
                    result = await mock_client.create_recipe(
                        name="Test Recipe",
                        ingredients="Test ingredients",
                        directions="Test directions",
                        generate_image=False,
                    )

        # Verify no image metadata was added
        assert result["photo"] == ""
        assert result["photo_hash"] == ""

    @pytest.mark.asyncio
    async def test_regenerate_recipe_image(self, mock_client, sample_image_bytes):
        """Test regenerating an image for an existing recipe."""
        # Mock existing recipe
        existing_recipe = {
            "uid": "TEST-UID",
            "name": "Existing Recipe",
            "description": "",
            "ingredients": "Test",
            "directions": "Test",
            "photo": "",
            "photo_hash": "",
            "in_trash": False,
        }

        # Mock image generator
        mock_image_gen = AsyncMock()
        mock_image_gen.generate_food_image = AsyncMock(
            return_value="https://example.com/regenerated.png"
        )
        mock_client.image_generator = mock_image_gen

        # Mock image download
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=sample_image_bytes)

        # Create async context manager mock for session.get()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_context)

        with patch.object(mock_client, "_get_session", return_value=mock_session):
            with patch.object(mock_client, "get_recipe_by_uid", return_value=existing_recipe):
                with patch.object(
                    mock_client, "_make_authenticated_request", new_callable=AsyncMock
                ):
                    result = await mock_client.regenerate_recipe_image(
                        uid="TEST-UID", custom_instructions=""
                    )

        # Verify new image was generated
        assert result["photo"].endswith(".png")
        assert len(result["photo_hash"]) == 64

    @pytest.mark.asyncio
    async def test_regenerate_image_with_custom_instructions(self, mock_client, sample_image_bytes):
        """Test regenerating image with custom styling instructions."""
        existing_recipe = {
            "uid": "TEST-UID",
            "name": "Test Recipe",
            "description": "",
            "ingredients": "Test",
            "directions": "Test",
            "photo": "",
            "photo_hash": "",
            "in_trash": False,
        }

        mock_image_gen = AsyncMock()
        mock_image_gen.generate_custom_food_image = AsyncMock(
            return_value="https://example.com/custom.png"
        )
        mock_client.image_generator = mock_image_gen

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=sample_image_bytes)

        # Create async context manager mock for session.get()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_context)

        with patch.object(mock_client, "_get_session", return_value=mock_session):
            with patch.object(mock_client, "get_recipe_by_uid", return_value=existing_recipe):
                with patch.object(
                    mock_client, "_make_authenticated_request", new_callable=AsyncMock
                ):
                    await mock_client.regenerate_recipe_image(
                        uid="TEST-UID",
                        custom_instructions="rustic style, darker lighting",
                    )

        # Verify custom image generator was called with instructions
        mock_image_gen.generate_custom_food_image.assert_called_once_with(
            recipe_name="Test Recipe",
            description="",
            custom_instructions="rustic style, darker lighting",
        )

    @pytest.mark.asyncio
    async def test_image_generation_failure_doesnt_block_recipe(self, mock_client):
        """Test that recipe creation succeeds even if image generation fails."""
        # Mock failing image generator
        mock_image_gen = AsyncMock()
        mock_image_gen.generate_food_image = AsyncMock(side_effect=Exception("API Error"))
        mock_client.image_generator = mock_image_gen

        mock_session = AsyncMock()

        with patch.object(mock_client, "_get_session", return_value=mock_session):
            with patch.object(mock_client, "_make_authenticated_request", new_callable=AsyncMock):
                # Mock recipe_title_exists to return None (no duplicate)
                with patch.object(
                    mock_client, "recipe_title_exists", new_callable=AsyncMock, return_value=None
                ):
                    # Should not raise exception
                    result = await mock_client.create_recipe(
                        name="Test Recipe",
                        ingredients="Test",
                        directions="Test",
                        generate_image=True,
                    )

        # Recipe should be created without image
        assert result["name"] == "Test Recipe"
        assert result["photo"] == ""  # No photo added due to failure
