import pytest
from paprika_mcp_server.image_generator import ImageGenerator


@pytest.fixture
def generator():
    """Create ImageGenerator instance for testing."""
    return ImageGenerator(api_token="test_token")


class TestBriefIngredientsPatternParsing:
    """Test parsing of Brief Ingredients pattern from descriptions."""

    def test_parse_with_brief_ingredients_and_description(self, generator):
        """Should extract both ingredients and description."""
        description = "Ingredients: Spaghetti, Pancetta, Eggs, Parmesan\n\nCreamy Italian pasta with crispy pancetta."

        ingredients, clean_desc = generator._parse_description_with_ingredients(description)

        assert ingredients == "Spaghetti, Pancetta, Eggs, Parmesan"
        assert clean_desc == "Creamy Italian pasta with crispy pancetta."

    def test_parse_with_brief_ingredients_only(self, generator):
        """Should extract ingredients when no additional description."""
        description = "Ingredients: Tomatoes, Basil, Mozzarella"

        ingredients, clean_desc = generator._parse_description_with_ingredients(description)

        assert ingredients == "Tomatoes, Basil, Mozzarella"
        assert clean_desc == ""

    def test_parse_without_brief_ingredients(self, generator):
        """Should return empty ingredients when pattern not present."""
        description = "A delicious Thai curry with coconut milk and fresh herbs."

        ingredients, clean_desc = generator._parse_description_with_ingredients(description)

        assert ingredients == ""
        assert clean_desc == "A delicious Thai curry with coconut milk and fresh herbs."

    def test_parse_with_single_newline_separator(self, generator):
        """Should handle single newline between ingredients and description."""
        description = "Ingredients: Chicken, Rice, Vegetables\nHealthy one-pot meal."

        ingredients, clean_desc = generator._parse_description_with_ingredients(description)

        assert ingredients == "Chicken, Rice, Vegetables"
        assert clean_desc == "Healthy one-pot meal."

    def test_parse_case_insensitive(self, generator):
        """Should match 'ingredient:' or 'Ingredients:' (case insensitive)."""
        description = "ingredient: Flour, Sugar, Butter\n\nClassic cookie recipe."

        ingredients, clean_desc = generator._parse_description_with_ingredients(description)

        assert ingredients == "Flour, Sugar, Butter"
        assert clean_desc == "Classic cookie recipe."

    def test_parse_empty_description(self, generator):
        """Should handle empty description gracefully."""
        ingredients, clean_desc = generator._parse_description_with_ingredients("")

        assert ingredients == ""
        assert clean_desc == ""

    def test_parse_with_extra_whitespace(self, generator):
        """Should trim extra whitespace from ingredients and description."""
        description = "  Ingredients:   Beef, Onions, Peppers  \n\n  Savory stir-fry.  "

        ingredients, clean_desc = generator._parse_description_with_ingredients(description)

        assert ingredients == "Beef, Onions, Peppers"
        assert clean_desc == "Savory stir-fry."


class TestImageGenerationWithBriefIngredients:
    """Test image generation integration with Brief Ingredients."""

    @pytest.mark.asyncio
    async def test_generate_with_brief_ingredients(self, generator, monkeypatch):
        """Should use ingredients in prompt when Brief Ingredients pattern detected."""
        captured_prompt = None

        async def mock_generate(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "https://example.com/image.jpg"

        monkeypatch.setattr(generator, "_generate_image", mock_generate)

        description = "Ingredients: Pasta, Tomatoes, Basil\n\nClassic Italian dish."
        await generator.generate_food_image("Spaghetti Pomodoro", description)

        # Should include ingredients at start of description
        assert "Pasta, Tomatoes, Basil" in captured_prompt
        assert "Classic Italian dish" in captured_prompt

    @pytest.mark.asyncio
    async def test_generate_without_brief_ingredients(self, generator, monkeypatch):
        """Should use description as-is when no Brief Ingredients pattern."""
        captured_prompt = None

        async def mock_generate(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "https://example.com/image.jpg"

        monkeypatch.setattr(generator, "_generate_image", mock_generate)

        description = "A spicy Thai curry with fresh vegetables."
        await generator.generate_food_image("Thai Green Curry", description)

        # Should use description as-is
        assert "A spicy Thai curry with fresh vegetables" in captured_prompt

    @pytest.mark.asyncio
    async def test_custom_generate_with_brief_ingredients(self, generator, monkeypatch):
        """Should work with custom instructions too."""
        captured_prompt = None

        async def mock_generate(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "https://example.com/image.jpg"

        monkeypatch.setattr(generator, "_generate_image", mock_generate)

        description = "Ingredients: Salmon, Lemon, Dill\n\nNordic-style fish."
        await generator.generate_custom_food_image(
            "Grilled Salmon", description, custom_instructions="rustic wooden plate"
        )

        # Should include ingredients, description, AND custom instructions
        assert "Salmon, Lemon, Dill" in captured_prompt
        assert "Nordic-style fish" in captured_prompt
        assert "rustic wooden plate" in captured_prompt
