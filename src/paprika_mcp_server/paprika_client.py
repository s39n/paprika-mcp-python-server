import base64
import gzip
import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class PaprikaAPIError(Exception):
    """Custom exception for Paprika API errors."""

    pass


class ValidationError(Exception):
    """Custom exception for input validation errors."""

    pass


class PaprikaClient:
    """Client for interacting with the Paprika Recipe Manager API."""

    BASE_URL = "https://paprikaapp.com/api"

    def __init__(
        self,
        username: str,
        password: str,
        image_generator: Optional[Any] = None
    ):
        """
        Initialize the Paprika client.

        Args:
            username: Paprika account email
            password: Paprika account password
            image_generator: Optional ImageGenerator instance for AI image generation
        """
        self.username = username
        self.password = password
        self.token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.image_generator = image_generator

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session

    async def authenticate(self) -> Optional[str]:
        """
        Authenticate with Paprika API and get access token.

        Returns:
            Authentication token

        Raises:
            PaprikaAPIError: If authentication fails
        """
        session = await self._get_session()

        login_data = {"email": self.username, "password": self.password}

        try:
            # Use v1 API for authentication (v2 returns "Unrecognized client")
            async with session.post(
                f"{self.BASE_URL}/v1/account/login",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status != 200:
                    raise PaprikaAPIError(f"Login failed with status {response.status}")

                result = await response.json()

                if "result" not in result or "token" not in result["result"]:
                    raise PaprikaAPIError("Invalid login response format")

                self.token = result["result"]["token"]
                logger.info("Successfully authenticated with Paprika API")
                return self.token

        except aiohttp.ClientError as e:
            raise PaprikaAPIError(f"Network error during authentication: {str(e)}")
        except json.JSONDecodeError:
            raise PaprikaAPIError("Invalid JSON response from login endpoint")

    async def _make_authenticated_request(
        self, method: str, endpoint: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Make an authenticated API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for aiohttp request

        Returns:
            JSON response data

        Raises:
            PaprikaAPIError: If request fails
        """
        if not self.token:
            await self.authenticate()

        session = await self._get_session()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"

        try:
            async with session.request(
                method, f"{self.BASE_URL}/v2{endpoint}", headers=headers, **kwargs
            ) as response:
                if response.status == 401:
                    # Token might be expired, re-authenticate
                    await self.authenticate()
                    headers["Authorization"] = f"Bearer {self.token}"

                    async with session.request(
                        method,
                        f"{self.BASE_URL}/v2{endpoint}",
                        headers=headers,
                        **kwargs,
                    ) as retry_response:
                        if retry_response.status != 200:
                            raise PaprikaAPIError(
                                f"Request failed with status {retry_response.status}"
                            )

                        return await retry_response.json()

                elif response.status != 200:
                    error_text = await response.text()
                    raise PaprikaAPIError(
                        f"Request failed with status {response.status}: {error_text}"
                    )

                return await response.json()

        except aiohttp.ClientError as e:
            raise PaprikaAPIError(f"Network error: {str(e)}")

    def _generate_uuid(self) -> str:
        """Generate a new uppercase UUID."""
        return str(uuid.uuid4()).upper()

    def _calculate_hash(self, recipe_dict: Dict[str, Any]) -> str:
        """
        Calculate SHA256 hash for a recipe object.

        Args:
            recipe_dict: Recipe data dictionary

        Returns:
            Hex-encoded SHA256 hash
        """
        # Remove hash field and sort keys for consistent hashing
        data = {k: v for k, v in recipe_dict.items() if k != "hash"}
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _gzip_json(self, data: Dict[str, Any]) -> bytes:
        """
        Compress JSON data with gzip.

        Args:
            data: Data to compress

        Returns:
            Gzipped JSON bytes
        """
        json_str = json.dumps(data)
        return gzip.compress(json_str.encode("utf-8"))

    async def _download_image(self, image_url: str) -> Optional[tuple[bytes, str]]:
        """
        Download an image from URL and return raw bytes + hash.

        Args:
            image_url: URL of the image to download

        Returns:
            Tuple of (raw image bytes, SHA256 hash in UPPERCASE),
            or None if download fails
        """
        try:
            session = await self._get_session()
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    # Calculate SHA256 hash of the raw image data (UPPERCASE for Paprika compatibility)
                    photo_hash = hashlib.sha256(image_data).hexdigest().upper()
                    logger.info(f"Successfully downloaded image ({len(image_data)} bytes, hash: {photo_hash[:8]}...)")
                    return (image_data, photo_hash)
                else:
                    logger.warning(f"Failed to download image: HTTP {response.status}")
                    return None
        except Exception as e:
            logger.warning(f"Error downloading image from {image_url}: {e}")
            return None

    async def _prepare_image_for_recipe(
        self,
        recipe: Dict[str, Any],
        image_url: str
    ) -> Optional[tuple[bytes, str]]:
        """
        Download image and prepare recipe metadata for photo upload.

        Paprika requires uploading photos as multipart file data:
        - photo: filename (generated UUID)
        - photo_hash: SHA256 hash of image bytes (UPPERCASE)
        - photo_large: filename for larger version
        - photo_url: can be left as None

        Args:
            recipe: Recipe object to modify (modified in-place)
            image_url: URL of the image to download

        Returns:
            Tuple of (image_bytes, filename) if successful, None otherwise
        """
        # Download image data
        photo_result = await self._download_image(image_url)

        if photo_result:
            image_bytes, photo_hash = photo_result

            # Generate a filename (UUID format like Paprika uses)
            photo_filename = f"{self._generate_uuid()}.png"

            # Set recipe metadata for photo
            # Note: photo_hash must be calculated BEFORE setting photo field
            recipe["photo"] = photo_filename
            recipe["photo_hash"] = photo_hash
            recipe["photo_large"] = photo_filename  # Can be description, we use filename
            recipe["photo_url"] = None  # Leave as None, we're uploading the file
            recipe["image_url"] = None  # Not used by Paprika

            logger.info(f"Prepared image for recipe: {recipe.get('name', 'Unknown')} (filename: {photo_filename})")
            return (image_bytes, photo_filename)
        else:
            logger.warning(f"Failed to download image from: {image_url}")
            return None

    def _create_recipe_object(
        self,
        name: str,
        ingredients: str,
        directions: str,
        description: str = "",
        notes: str = "",
        servings: str = "",
        prep_time: str = "",
        cook_time: str = "",
        difficulty: str = "",
        uid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a recipe object with all required fields.

        Args:
            name: Recipe name
            ingredients: Recipe ingredients
            directions: Cooking directions
            description: Recipe description
            notes: Additional notes
            servings: Number of servings
            prep_time: Preparation time
            cook_time: Cooking time
            difficulty: Difficulty level
            uid: Recipe UID (generated if not provided)

        Returns:
            Complete recipe object
        """
        recipe = {
            "uid": uid or self._generate_uuid(),
            "name": name,
            "ingredients": ingredients,
            "directions": directions,
            "description": description,
            "notes": notes,
            "servings": servings,
            "prep_time": prep_time,
            "cook_time": cook_time,
            "total_time": "",
            "difficulty": difficulty,
            "source": "",
            "source_url": "",
            "categories": [],
            "rating": 0,
            "nutritional_info": "",
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "in_trash": False,
            "is_pinned": False,
            "on_favorites": False,
            "on_grocery_list": False,
            "image_url": "",
            "photo": "",
            "photo_hash": "",
            "photo_large": None,
            "photo_url": None,
            "scale": None,
        }

        # Calculate and set hash
        recipe["hash"] = self._calculate_hash(recipe)
        return recipe

    async def get_recipe_by_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        Get a single recipe by UID.

        Args:
            uid: Recipe UID

        Returns:
            Recipe data if found, None otherwise

        Raises:
            PaprikaAPIError: If request fails
        """
        try:
            response = await self._make_authenticated_request(
                "GET", f"/sync/recipe/{uid}/"
            )

            recipe_data = response.get("result", {})

            if not recipe_data or recipe_data.get("in_trash", False):
                return None

            logger.info(f"Successfully fetched recipe by UID: {uid}")
            return recipe_data

        except Exception as e:
            logger.error(f"Failed to get recipe by UID {uid}: {str(e)}")
            return None

    async def get_recipe_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """
        Get a single recipe by exact title match (case-sensitive).

        Args:
            title: Recipe title to search for

        Returns:
            Recipe data if found, None otherwise

        Raises:
            PaprikaAPIError: If request fails
        """
        try:
            # Get all recipes and filter by title
            response = await self._make_authenticated_request("GET", "/sync/recipes")
            recipe_list = response.get("result", [])

            if not recipe_list:
                return None

            # Search for recipe with matching title
            for recipe_info in recipe_list:
                uid = recipe_info["uid"]

                try:
                    recipe_response = await self._make_authenticated_request(
                        "GET", f"/sync/recipe/{uid}/"
                    )

                    recipe_data = recipe_response.get("result", {})

                    # Check for exact title match (case-sensitive) and not in trash
                    if (
                        recipe_data.get("name") == title
                        and not recipe_data.get("in_trash", False)
                    ):
                        logger.info(f"Successfully found recipe by title: {title}")
                        return recipe_data

                except Exception as e:
                    logger.warning(f"Failed to fetch recipe {uid}: {str(e)}")
                    continue

            logger.info(f"No recipe found with title: {title}")
            return None

        except Exception as e:
            logger.error(f"Failed to get recipe by title {title}: {str(e)}")
            raise PaprikaAPIError(f"Failed to get recipe by title: {str(e)}")

    async def recipe_title_exists(self, title: str) -> Optional[str]:
        """
        Check if a recipe with the given title already exists.

        Args:
            title: Recipe title to check

        Returns:
            Recipe UID if title exists, None otherwise

        Raises:
            PaprikaAPIError: If request fails
        """
        recipe = await self.get_recipe_by_title(title)
        return recipe.get("uid") if recipe else None

    def _validate_recipe_name(self, name: str) -> None:
        """
        Validate recipe name.

        Args:
            name: Recipe name to validate

        Raises:
            ValidationError: If name is invalid
        """
        if not name:
            raise ValidationError("Recipe name cannot be empty")

        if not isinstance(name, str):
            raise ValidationError("Recipe name must be a string")

        name_stripped = name.strip()
        if not name_stripped:
            raise ValidationError("Recipe name cannot be empty or whitespace only")

        if len(name_stripped) > 200:
            raise ValidationError("Recipe name must be 200 characters or less")

    def _validate_ingredients(self, ingredients: Any) -> None:
        """
        Validate ingredients.

        Args:
            ingredients: Ingredients to validate (string or list)

        Raises:
            ValidationError: If ingredients are invalid
        """
        if not ingredients:
            raise ValidationError("Ingredients must be provided")

        # Accept both string and list formats
        if isinstance(ingredients, list):
            if not ingredients:
                raise ValidationError("Ingredients list cannot be empty")
            for i, ingredient in enumerate(ingredients):
                if not isinstance(ingredient, str) or not ingredient.strip():
                    raise ValidationError(
                        f"Ingredient at position {i} must be a non-empty string"
                    )
        elif isinstance(ingredients, str):
            if not ingredients.strip():
                raise ValidationError("Ingredients cannot be empty or whitespace only")
        else:
            raise ValidationError("Ingredients must be a string or list of strings")

    def _validate_directions(self, directions: str) -> None:
        """
        Validate recipe directions.

        Args:
            directions: Directions to validate

        Raises:
            ValidationError: If directions are invalid
        """
        if not directions:
            raise ValidationError("Recipe directions cannot be empty")

        if not isinstance(directions, str):
            raise ValidationError("Recipe directions must be a string")

        if not directions.strip():
            raise ValidationError(
                "Recipe directions cannot be empty or whitespace only"
            )

    def _validate_numeric_field(
        self, value: Any, field_name: str, min_val: int = 0
    ) -> None:
        """
        Validate numeric fields (servings, times).

        Args:
            value: Value to validate
            field_name: Name of the field (for error messages)
            min_val: Minimum allowed value (default: 0)

        Raises:
            ValidationError: If value is invalid
        """
        if value is None or value == "":
            return  # Optional fields can be empty

        # Try to convert string to int
        if isinstance(value, str):
            try:
                value = int(value)
            except ValueError:
                raise ValidationError(
                    f"{field_name} must be a number, got: '{value}'"
                )

        if not isinstance(value, int):
            raise ValidationError(f"{field_name} must be an integer")

        if value < min_val:
            if min_val == 0:
                raise ValidationError(f"{field_name} cannot be negative")
            else:
                raise ValidationError(
                    f"{field_name} must be at least {min_val}, got: {value}"
                )

    def _validate_string_field(
        self, value: Any, field_name: str, required: bool = False
    ) -> None:
        """
        Validate optional string fields.

        Args:
            value: Value to validate
            field_name: Name of the field (for error messages)
            required: Whether field is required

        Raises:
            ValidationError: If value is invalid
        """
        if value is None or value == "":
            if required:
                raise ValidationError(f"{field_name} is required")
            return  # Optional fields can be empty

        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string")

    async def delete_recipe(self, uid: str) -> Dict[str, Any]:
        """
        Delete a recipe by moving it to trash (soft delete).

        Args:
            uid: Recipe UID to delete

        Returns:
            Deleted recipe data with confirmation

        Raises:
            PaprikaAPIError: If deletion fails or recipe not found
        """
        try:
            # First, get the existing recipe
            recipe_data = await self.get_recipe_by_uid(uid)

            if not recipe_data:
                raise PaprikaAPIError(f"Recipe with UID '{uid}' not found")

            # Check if already in trash
            if recipe_data.get("in_trash", False):
                return {
                    "already_deleted": True,
                    "name": recipe_data.get("name", ""),
                    "uid": uid,
                }

            # Set in_trash to True
            recipe_data["in_trash"] = True
            recipe_data["created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            recipe_data["hash"] = self._calculate_hash(recipe_data)

            # Gzip the recipe data
            gzipped_data = self._gzip_json(recipe_data)

            # Create multipart form data
            data = aiohttp.FormData()
            data.add_field(
                "data", gzipped_data, content_type="application/octet-stream"
            )

            await self._make_authenticated_request(
                "POST", f"/sync/recipe/{uid}/", data=data
            )

            logger.info(f"Successfully deleted recipe: {recipe_data['name']}")
            return recipe_data

        except Exception as e:
            logger.error(f"Failed to delete recipe {uid}: {str(e)}")
            raise PaprikaAPIError(f"Failed to delete recipe: {str(e)}")

    async def create_recipe(
        self,
        name: str,
        ingredients: str,
        directions: str,
        description: str = "",
        notes: str = "",
        servings: str = "",
        prep_time: str = "",
        cook_time: str = "",
        difficulty: str = "",
        generate_image: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a new recipe in Paprika.

        Args:
            name: Recipe name
            ingredients: Recipe ingredients (one per line)
            directions: Cooking directions
            description: Recipe description
            notes: Additional notes
            servings: Number of servings
            prep_time: Preparation time
            cook_time: Cooking time
            difficulty: Difficulty level
            generate_image: Whether to auto-generate AI food photography (default: True)

        Returns:
            Created recipe data

        Raises:
            ValidationError: If input validation fails
            PaprikaAPIError: If creation fails or duplicate title exists
        """
        # Validate required fields
        self._validate_recipe_name(name)
        self._validate_ingredients(ingredients)
        self._validate_directions(directions)

        # Validate optional string fields
        self._validate_string_field(description, "Description")
        self._validate_string_field(notes, "Notes")
        self._validate_string_field(difficulty, "Difficulty")

        # Validate numeric fields
        if servings:
            self._validate_numeric_field(servings, "Servings", min_val=1)
        if prep_time:
            # For time fields, we accept string format like "15 mins"
            # Just validate it's a string if provided
            self._validate_string_field(prep_time, "Prep time")
        if cook_time:
            self._validate_string_field(cook_time, "Cook time")

        # Check for duplicate title
        existing_uid = await self.recipe_title_exists(name)
        if existing_uid:
            logger.warning(f"Duplicate recipe title detected: {name} (UID: {existing_uid})")
            raise PaprikaAPIError(
                f"Recipe '{name}' already exists (UID: {existing_uid}). "
                "Please choose a different name or use update_recipe to modify the existing one."
            )

        # Generate AI image BEFORE creating recipe (if enabled)
        image_url = None
        image_data = None
        if generate_image and self.image_generator:
            try:
                logger.info(f"Generating AI image for recipe: {name}")
                image_url = await self.image_generator.generate_food_image(
                    name, description
                )

                if not image_url:
                    logger.warning(f"Image generation returned no URL for: {name}")
            except Exception as e:
                # Never fail recipe creation due to image generation
                logger.warning(
                    f"Image generation failed for '{name}': {e}",
                    exc_info=True
                )

        # Create recipe object
        recipe = self._create_recipe_object(
            name=name,
            ingredients=ingredients,
            directions=directions,
            description=description,
            notes=notes,
            servings=servings,
            prep_time=prep_time,
            cook_time=cook_time,
            difficulty=difficulty,
        )

        # Prepare image for upload if generation succeeded
        photo_filename = None
        if image_url:
            image_result = await self._prepare_image_for_recipe(recipe, image_url)
            if image_result:
                image_data, photo_filename = image_result

        # Calculate hash after all fields are set
        recipe["hash"] = self._calculate_hash(recipe)

        # Create multipart form data with recipe + optional photo
        data = aiohttp.FormData()
        data.add_field("data", self._gzip_json(recipe), content_type="application/octet-stream")

        # Add photo_upload field if we have an image (required for Paprika to accept photos)
        if image_data and photo_filename:
            data.add_field(
                "photo_upload",
                image_data,
                filename=photo_filename,
                content_type="image/png"
            )
            logger.info(f"Uploading recipe with photo_upload field: {photo_filename}")

        try:
            await self._make_authenticated_request(
                "POST", f"/sync/recipe/{recipe['uid']}/", data=data
            )

            if image_url:
                logger.info(f"Successfully created recipe '{name}' with AI-generated image")
            else:
                logger.info(f"Successfully created recipe: {name}")

            return recipe

        except Exception as e:
            logger.error(f"Failed to create recipe {name}: {str(e)}")
            raise PaprikaAPIError(f"Failed to create recipe: {str(e)}")

    async def update_recipe(
        self,
        uid: str,
        name: str,
        ingredients: str,
        directions: str,
        description: str = "",
        notes: str = "",
        servings: str = "",
        prep_time: str = "",
        cook_time: str = "",
        difficulty: str = "",
    ) -> Dict[str, Any]:
        """
        Update an existing recipe in Paprika.

        Args:
            uid: Recipe UID to update
            name: Recipe name
            ingredients: Recipe ingredients
            directions: Cooking directions
            description: Recipe description
            notes: Additional notes
            servings: Number of servings
            prep_time: Preparation time
            cook_time: Cooking time
            difficulty: Difficulty level

        Returns:
            Updated recipe data

        Raises:
            PaprikaAPIError: If update fails
        """
        recipe = self._create_recipe_object(
            name=name,
            ingredients=ingredients,
            directions=directions,
            description=description,
            notes=notes,
            servings=servings,
            prep_time=prep_time,
            cook_time=cook_time,
            difficulty=difficulty,
            uid=uid,
        )

        # Gzip the recipe data
        gzipped_data = self._gzip_json(recipe)

        # Create multipart form data
        data = aiohttp.FormData()
        data.add_field("data", gzipped_data, content_type="application/octet-stream")

        try:
            await self._make_authenticated_request(
                "POST", f"/sync/recipe/{uid}/", data=data
            )

            logger.info(f"Successfully updated recipe: {name}")
            return recipe

        except Exception as e:
            logger.error(f"Failed to update recipe {name}: {str(e)}")
            raise PaprikaAPIError(f"Failed to update recipe: {str(e)}")

    async def update_recipe_partial(self, uid: str, **kwargs) -> Dict[str, Any]:
        """
        Partially update an existing recipe in Paprika.
        Only updates the fields that are provided.

        Args:
            uid: Recipe UID to update
            **kwargs: Fields to update (name, ingredients, directions, etc.)

        Returns:
            Updated recipe data

        Raises:
            ValidationError: If input validation fails
            PaprikaAPIError: If update fails
        """
        # Validate UID
        if not uid or not isinstance(uid, str) or not uid.strip():
            raise ValidationError("Recipe UID is required and must be a non-empty string")

        # Validate provided fields
        for field, value in kwargs.items():
            if value is None:
                continue  # Skip None values

            # Validate even if empty string (some fields shouldn't be empty)
            if field == "name":
                self._validate_recipe_name(value)
            elif field == "ingredients":
                self._validate_ingredients(value)
            elif field == "directions":
                self._validate_directions(value)
            elif field in ["description", "notes", "difficulty", "prep_time", "cook_time"]:
                if value != "":  # Only validate non-empty optional fields
                    self._validate_string_field(value, field.replace("_", " ").title())
            elif field == "servings":
                if value != "":  # Only validate non-empty servings
                    self._validate_numeric_field(value, "Servings", min_val=1)

        try:
            # First, get the existing recipe
            response = await self._make_authenticated_request(
                "GET", f"/sync/recipe/{uid}/"
            )
            existing_recipe = response.get("result", {})

            if not existing_recipe:
                raise PaprikaAPIError(f"Recipe with UID {uid} not found")

            # Update only the provided fields
            for field, value in kwargs.items():
                if value is not None and value != "":
                    existing_recipe[field] = value

            # Recalculate hash and update timestamp
            existing_recipe["created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            existing_recipe["hash"] = self._calculate_hash(existing_recipe)

            # Gzip the recipe data
            gzipped_data = self._gzip_json(existing_recipe)

            # Create multipart form data
            data = aiohttp.FormData()
            data.add_field(
                "data", gzipped_data, content_type="application/octet-stream"
            )

            await self._make_authenticated_request(
                "POST", f"/sync/recipe/{uid}/", data=data
            )

            logger.info(
                f"Successfully partially updated recipe: {existing_recipe['name']}"
            )
            return existing_recipe

        except Exception as e:
            logger.error(f"Failed to partially update recipe {uid}: {str(e)}")
            raise PaprikaAPIError(f"Failed to partially update recipe: {str(e)}")

    async def list_recipes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        List recipes from Paprika.

        Args:
            limit: Maximum number of recipes to return

        Returns:
            List of recipe data

        Raises:
            PaprikaAPIError: If listing fails
        """
        try:
            # First get the list of recipe UIDs
            response = await self._make_authenticated_request("GET", "/sync/recipes")
            recipe_list = response.get("result", [])

            if not recipe_list:
                return []

            # Limit the number of recipes to fetch
            recipe_list = recipe_list[:limit]

            # Fetch full recipe data for each UID
            recipes = []
            for recipe_info in recipe_list:
                uid = recipe_info["uid"]

                try:
                    recipe_response = await self._make_authenticated_request(
                        "GET", f"/sync/recipe/{uid}/"
                    )

                    recipe_data = recipe_response.get("result", {})

                    # Skip recipes in trash
                    if recipe_data.get("in_trash", False):
                        continue

                    recipes.append(recipe_data)

                except Exception as e:
                    logger.warning(f"Failed to fetch recipe {uid}: {str(e)}")
                    continue

            logger.info(f"Successfully fetched {len(recipes)} recipes")
            return recipes

        except Exception as e:
            logger.error(f"Failed to list recipes: {str(e)}")
            raise PaprikaAPIError(f"Failed to list recipes: {str(e)}")

    async def regenerate_recipe_image(
        self,
        uid: str,
        custom_instructions: str = ""
    ) -> Dict[str, Any]:
        """
        Regenerate AI image for an existing recipe with optional custom styling.

        Args:
            uid: Recipe UID
            custom_instructions: Optional styling instructions
                (e.g., "rustic style, less cream visible")

        Returns:
            Updated recipe data with new image

        Raises:
            PaprikaAPIError: If regeneration fails or recipe not found
            ValueError: If image_generator is not configured
        """
        if not self.image_generator:
            raise ValueError(
                "Image generator not configured. "
                "Set REPLICATE_API_TOKEN environment variable."
            )

        try:
            # Get existing recipe
            recipe_data = await self.get_recipe_by_uid(uid)

            if not recipe_data:
                raise PaprikaAPIError(f"Recipe with UID '{uid}' not found")

            recipe_name = recipe_data.get("name", "")
            recipe_description = recipe_data.get("description", "")

            # Generate new image with custom instructions
            logger.info(
                f"Regenerating image for recipe: {recipe_name} "
                f"(instructions: {custom_instructions or 'none'})"
            )

            if custom_instructions:
                image_url = await self.image_generator.generate_custom_food_image(
                    recipe_name=recipe_name,
                    description=recipe_description,
                    custom_instructions=custom_instructions,
                )
            else:
                image_url = await self.image_generator.generate_food_image(
                    recipe_name=recipe_name, description=recipe_description
                )

            if not image_url:
                raise PaprikaAPIError(
                    f"Image generation failed for recipe '{recipe_name}'"
                )

            # Prepare image for upload
            image_result = await self._prepare_image_for_recipe(recipe_data, image_url)

            if not image_result:
                raise PaprikaAPIError(
                    f"Failed to download image from URL: {image_url}"
                )

            image_bytes, photo_filename = image_result

            # Update timestamp and recalculate hash
            recipe_data["created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            recipe_data["hash"] = self._calculate_hash(recipe_data)

            # Debug: Log what we're uploading
            logger.info(
                f"Uploading recipe with photo_upload: "
                f"photo='{recipe_data.get('photo')}', "
                f"photo_hash='{recipe_data.get('photo_hash')}', "
                f"photo_large='{recipe_data.get('photo_large')}'"
            )

            # Create multipart form data with recipe + photo
            data = aiohttp.FormData()
            data.add_field(
                "data", self._gzip_json(recipe_data), content_type="application/octet-stream"
            )
            data.add_field(
                "photo_upload",
                image_bytes,
                filename=photo_filename,
                content_type="image/png"
            )

            await self._make_authenticated_request(
                "POST", f"/sync/recipe/{uid}/", data=data
            )

            logger.info(f"Successfully regenerated image for recipe: {recipe_name}")
            return recipe_data

        except Exception as e:
            logger.error(f"Failed to regenerate image for recipe {uid}: {str(e)}")
            raise PaprikaAPIError(f"Failed to regenerate image: {str(e)}")

    async def _get_sync_entity(self, entity: str) -> List[Dict[str, Any]]:
        """GET /sync/{entity}/ and return the 'result' list (read-only collections)."""
        response = await self._make_authenticated_request("GET", f"/sync/{entity}/")
        result = response.get("result", [])
        return result or []

    async def get_menus(self) -> List[Dict[str, Any]]:
        """Return all saved Menus (reusable meal-plan collections)."""
        try:
            return await self._get_sync_entity("menus")
        except Exception as e:
            logger.error(f"Failed to get menus: {str(e)}")
            raise PaprikaAPIError(f"Failed to get menus: {str(e)}")

    async def get_menu_items(self) -> List[Dict[str, Any]]:
        """Return all menu items (recipes assigned within menus)."""
        try:
            return await self._get_sync_entity("menuitems")
        except Exception as e:
            logger.error(f"Failed to get menu items: {str(e)}")
            raise PaprikaAPIError(f"Failed to get menu items: {str(e)}")

    async def get_meals(self) -> List[Dict[str, Any]]:
        """Return all meals scheduled on the meal-planner calendar."""
        try:
            return await self._get_sync_entity("meals")
        except Exception as e:
            logger.error(f"Failed to get meals: {str(e)}")
            raise PaprikaAPIError(f"Failed to get meals: {str(e)}")

    _DINNER_TYPE_UID_FALLBACK = "216713D08860CFA0D9787EA5C6CEBC8A8F5B73777F91C904853AC234BB9DF642"

    async def _get_type_uid(self, meal_type_int: int):
        """Return the account's type_uid for a meal type (0=bfast,1=lunch,2=dinner,3=snack). Scans existing meals once, cached."""
        cache = getattr(self, "_type_uid_cache", None)
        if cache is None:
            cache = {}
            try:
                for m in await self._get_sync_entity("meals"):
                    t, tu = m.get("type"), m.get("type_uid")
                    if t is not None and tu and t not in cache:
                        cache[t] = tu
            except Exception as e:
                logger.warning(f"Could not build type_uid cache: {str(e)}")
            self._type_uid_cache = cache
        if meal_type_int in cache:
            return cache[meal_type_int]
        return self._DINNER_TYPE_UID_FALLBACK if meal_type_int == 2 else None

    async def create_meal(self, date: str, name: str, recipe_uid=None, meal_type: int = 2,
                          type_uid=None, order_flag: int = 0, uid=None) -> Dict[str, Any]:
        """Schedule a meal on the planner calendar. date 'YYYY-MM-DD' or full timestamp."""
        if date and len(date) == 10:
            date = f"{date} 00:00:00"
        if type_uid is None:
            type_uid = await self._get_type_uid(meal_type)
        meal = {
            "uid": uid or self._generate_uuid(),
            "recipe_uid": recipe_uid or None,
            "date": date,
            "type": meal_type,
            "name": name,
            "order_flag": order_flag,
            "type_uid": type_uid,
            "scale": None,
            "is_ingredient": False,
        }
        meal["hash"] = self._calculate_hash(meal)
        data = aiohttp.FormData()
        data.add_field("data", self._gzip_json(meal), content_type="application/octet-stream")
        await self._make_authenticated_request("POST", f"/sync/meal/{meal['uid']}/", data=data)
        logger.info(f"Scheduled meal '{name}' on {date}")
        return meal

    async def create_menu(self, name: str, notes: str = "", days: int = 7,
                          order_flag: int = 0, uid=None) -> Dict[str, Any]:
        """Create a new reusable Menu."""
        menu = {
            "uid": uid or self._generate_uuid(),
            "name": name,
            "notes": notes,
            "order_flag": order_flag,
            "days": days,
        }
        menu["hash"] = self._calculate_hash(menu)
        data = aiohttp.FormData()
        data.add_field("data", self._gzip_json(menu), content_type="application/octet-stream")
        await self._make_authenticated_request("POST", f"/sync/menu/{menu['uid']}/", data=data)
        logger.info(f"Created menu '{name}'")
        return menu

    async def create_menu_item(self, menu_uid: str, name: str, day: int = 1, recipe_uid=None,
                               meal_type: int = 2, type_uid=None, order_flag: int = 0, uid=None) -> Dict[str, Any]:
        """Add an item (recipe or free text) to a Menu on a given day."""
        if type_uid is None:
            type_uid = await self._get_type_uid(meal_type)
        item = {
            "uid": uid or self._generate_uuid(),
            "name": name,
            "order_flag": order_flag,
            "recipe_uid": recipe_uid or None,
            "menu_uid": menu_uid,
            "type_uid": type_uid,
            "day": day,
            "scale": None,
            "is_ingredient": False,
        }
        item["hash"] = self._calculate_hash(item)
        data = aiohttp.FormData()
        data.add_field("data", self._gzip_json(item), content_type="application/octet-stream")
        await self._make_authenticated_request("POST", f"/sync/menuitem/{item['uid']}/", data=data)
        logger.info(f"Added menu item '{name}' to menu {menu_uid}")
        return item

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
