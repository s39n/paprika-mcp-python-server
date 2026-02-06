import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class ImageGenerator:
    """
    Generates AI-powered food photography using Black Forest Labs FLUX 2 Klein.

    Cost: ~$0.003 per image
    Generation time: 1-3 seconds typical, 60s timeout
    """

    # FLUX 2 Klein 4B model on Replicate
    DEFAULT_MODEL = "black-forest-labs/flux-2-klein-4b"

    # Base prompt template for close-up, vibrant food photography with generous portions
    BASE_PROMPT_TEMPLATE = (
        "Professional close-up food photography of {recipe_name}: {description}. "
        "Extreme close-up with food filling entire frame, "
        "generous hearty home-cooked portions, "
        "vibrant saturated colors, bright natural lighting, "
        "authentic, macro lens perspective, "
        "high resolution, appetizing"
    )

    def __init__(self, api_token: str, model: str = DEFAULT_MODEL, timeout: int = 60):
        """
        Initialize the image generator.

        Args:
            api_token: Replicate API token
            model: Replicate model ID (defaults to FLUX 2 Klein 4B)
            timeout: Maximum generation time in seconds (default: 60)
        """
        self.api_token = api_token
        self.model = model
        self.timeout = timeout
        self._replicate_client = None

    def _get_replicate_client(self):
        """Lazy-load replicate client to avoid import errors if not installed."""
        if self._replicate_client is None:
            try:
                import replicate

                # Create client instance with API token
                self._replicate_client = replicate.Client(api_token=self.api_token)
            except ImportError:
                logger.error("replicate package not installed. Run: pip install replicate")
                raise
        return self._replicate_client

    def _parse_description_with_ingredients(self, description: str) -> tuple[str, str]:
        """
        Parse description to extract brief ingredients if present.

        Supports the "Brief Ingredients" pattern:
        "Ingredients: item1, item2, item3\n\n[rest of description]"

        Args:
            description: Recipe description (may contain brief ingredients)

        Returns:
            Tuple of (ingredients_text, description_text)
            - ingredients_text: Extracted ingredients or empty string
            - description_text: Description without the ingredients prefix
        """
        if not description:
            return "", ""

        # Check for "Ingredients: ..." pattern at start of description
        match = re.match(
            r"^Ingredients?\s*:\s*([^\n]+)(?:\n\n?(.*))?$",
            description.strip(),
            re.IGNORECASE | re.DOTALL,
        )

        if match:
            ingredients = match.group(1).strip()
            remaining_desc = match.group(2).strip() if match.group(2) else ""
            return ingredients, remaining_desc

        # No brief ingredients pattern found
        return "", description.strip()

    def _build_description_for_prompt(self, recipe_name: str, description: str) -> str:
        """
        Build description text for image generation prompt.

        Parses description for Brief Ingredients pattern and combines appropriately.

        Args:
            recipe_name: Recipe name (fallback if no description)
            description: Recipe description (may contain Brief Ingredients)

        Returns:
            Description text ready for prompt template
        """
        ingredients, clean_desc = self._parse_description_with_ingredients(description)

        if ingredients:
            if clean_desc:
                desc = f"{ingredients}. {clean_desc}"
            else:
                desc = ingredients
            logger.info(f"Using brief ingredients: {ingredients[:50]}...")
            return desc

        if description:
            return description.strip()

        return recipe_name.strip()

    async def generate_food_image(self, recipe_name: str, description: str = "") -> Optional[str]:
        """
        Generate a professional food photo for a recipe using base prompt template.

        Automatically detects and uses "Brief Ingredients" pattern if present in description:
        "Ingredients: item1, item2, item3\\n\\n[description]"

        Args:
            recipe_name: Name of the recipe (e.g., "Spaghetti Carbonara")
            description: Recipe description for better context (optional)

        Returns:
            Image URL if generation succeeds, None if it fails
        """
        if not recipe_name or not recipe_name.strip():
            logger.warning("Cannot generate image: empty recipe name")
            return None

        desc = self._build_description_for_prompt(recipe_name, description)
        prompt = self.BASE_PROMPT_TEMPLATE.format(recipe_name=recipe_name.strip(), description=desc)

        try:
            logger.info(f"Generating image for recipe: {recipe_name}")
            url = await self._generate_image(prompt)
            logger.info(f"Successfully generated image for: {recipe_name}")
            return url

        except Exception as e:
            logger.warning(f"Image generation failed for '{recipe_name}': {e}", exc_info=True)
            return None

    async def generate_custom_food_image(
        self, recipe_name: str, description: str = "", custom_instructions: str = ""
    ) -> Optional[str]:
        """
        Generate a food photo with custom styling instructions.

        Automatically detects and uses "Brief Ingredients" pattern if present in description:
        "Ingredients: item1, item2, item3\\n\\n[description]"

        Args:
            recipe_name: Name of the recipe
            description: Recipe description for better context (optional)
            custom_instructions: Additional styling instructions
                (e.g., "rustic style, less cream visible")

        Returns:
            Image URL if generation succeeds, None if it fails
        """
        if not recipe_name or not recipe_name.strip():
            logger.warning("Cannot generate image: empty recipe name")
            return None

        desc = self._build_description_for_prompt(recipe_name, description)
        base_prompt = self.BASE_PROMPT_TEMPLATE.format(
            recipe_name=recipe_name.strip(), description=desc
        )

        if custom_instructions and custom_instructions.strip():
            prompt = f"{base_prompt}, {custom_instructions.strip()}"
        else:
            prompt = base_prompt

        try:
            logger.info(
                f"Generating custom image for recipe: {recipe_name} "
                f"(instructions: {custom_instructions or 'none'})"
            )
            url = await self._generate_image(prompt)
            logger.info(f"Successfully generated custom image for: {recipe_name}")
            return url

        except Exception as e:
            logger.warning(
                f"Custom image generation failed for '{recipe_name}': {e}",
                exc_info=True,
            )
            return None

    async def _generate_image(self, prompt: str) -> str:
        """
        Internal method to call FLUX 2 Klein via Replicate API and generate image.

        Args:
            prompt: Complete prompt for image generation

        Returns:
            Image URL from Replicate

        Raises:
            Exception: If generation fails (timeout, API error, etc.)
        """
        replicate = self._get_replicate_client()

        # Run generation in thread pool to avoid blocking
        # (replicate SDK is synchronous)
        loop = asyncio.get_event_loop()

        try:
            # Run with timeout
            output = await asyncio.wait_for(
                loop.run_in_executor(None, self._run_replicate_sync, prompt),
                timeout=self.timeout,
            )

            # Replicate v1.0+ returns FileOutput objects or lists of them
            # Extract URL from the output
            if isinstance(output, list) and len(output) > 0:
                # List of FileOutput objects or URLs
                first_item = output[0]
                if hasattr(first_item, "url"):
                    return first_item.url
                elif isinstance(first_item, str):
                    return first_item
                else:
                    raise ValueError(f"Unexpected list item type: {type(first_item)}")
            elif isinstance(output, str):
                # Plain URL string
                return output
            elif hasattr(output, "url"):
                # Single FileOutput object
                return output.url
            else:
                raise ValueError(f"Unexpected output format: {type(output)}")

        except asyncio.TimeoutError:
            raise Exception(f"Image generation timed out after {self.timeout}s")

    def _run_replicate_sync(self, prompt: str):
        """
        Synchronous wrapper for Replicate API call.

        Args:
            prompt: Image generation prompt

        Returns:
            Replicate API output (URL or list of URLs)
        """
        client = self._get_replicate_client()

        # Run the FLUX 2 Klein model
        output = client.run(
            self.model,
            input={
                "prompt": prompt,
            },
        )

        return output
