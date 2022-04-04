import json
import re
from io import BytesIO
from zipfile import ZipFile

from cookbook.helper.image_processing import get_filetype
from cookbook.helper.ingredient_parser import IngredientParser
from cookbook.helper.recipe_url_import import iso_duration_to_minutes
from cookbook.integration.integration import Integration
from cookbook.models import Ingredient, Keyword, Recipe, Step


class NextcloudCookbook(Integration):

    def import_file_name_filter(self, zip_info_object):
        return zip_info_object.filename.endswith('.json')

    def get_recipe_from_file(self, file):
        recipe_json = json.loads(file.getvalue().decode("utf-8"))

        description = '' if len(recipe_json['description'].strip()) > 500 else recipe_json['description'].strip()

        recipe = Recipe.objects.create(
            name=recipe_json['name'].strip(), description=description,
            created_by=self.request.user, internal=True,
            servings=recipe_json['recipeYield'], space=self.request.space)

        try:
            recipe.working_time = iso_duration_to_minutes(recipe_json['prepTime'])
            recipe.waiting_time = iso_duration_to_minutes(recipe_json['cookTime'])
        except Exception:
            pass

        if 'url' in recipe_json:
            recipe.source_url = recipe_json['url'].strip()

        if 'recipeCategory' in recipe_json:
            try:
                recipe.keywords.add(Keyword.objects.get_or_create(space=self.request.space, name=recipe_json['recipeCategory'])[0])
            except Exception:
                pass

        if 'keywords' in recipe_json:
            try:
                for x in recipe_json['keywords'].split(','):
                    recipe.keywords.add(Keyword.objects.get_or_create(space=self.request.space, name=x)[0])
            except Exception:
                pass

        ingredients_added = False
        for s in recipe_json['recipeInstructions']:
            step = Step.objects.create(
                instruction=s, space=self.request.space,
            )
            if not ingredients_added:
                if len(recipe_json['description'].strip()) > 500:
                    step.instruction = recipe_json['description'].strip() + '\n\n' + step.instruction

                ingredients_added = True

                ingredient_parser = IngredientParser(self.request, True)
                for ingredient in recipe_json['recipeIngredient']:
                    amount, unit, food, note = ingredient_parser.parse(ingredient)
                    f = ingredient_parser.get_food(food)
                    u = ingredient_parser.get_unit(unit)
                    step.ingredients.add(Ingredient.objects.create(
                        food=f, unit=u, amount=amount, note=note, original_text=ingredient, space=self.request.space,
                    ))
            recipe.steps.add(step)

        if 'nutrition' in recipe_json:
            try:
                recipe.nutrition.calories = recipe_json['nutrition']['calories'].replace(' kcal', '').replace(' ', '')
                recipe.nutrition.proteins = recipe_json['nutrition']['calories'].replace(' g', '').replace(',', '.').replace(' ', '')
                recipe.nutrition.fats = recipe_json['nutrition']['calories'].replace(' g', '').replace(',', '.').replace(' ', '')
                recipe.nutrition.carbohydrates = recipe_json['nutrition']['calories'].replace(' g', '').replace(',', '.').replace(' ', '')
            except Exception:
                pass

        for f in self.files:
            if '.zip' in f['name']:
                import_zip = ZipFile(f['file'])
                for z in import_zip.filelist:
                    if re.match(f'^(.)+{recipe.name}/full.jpg$', z.filename):
                        self.import_recipe_image(recipe, BytesIO(import_zip.read(z.filename)), filetype=get_filetype(z.filename))

        return recipe

    def get_file_from_recipe(self, recipe):
        raise NotImplementedError('Method not implemented in storage integration')
