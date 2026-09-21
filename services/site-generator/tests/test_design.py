import pytest

from site_generator.design import THEMES, contrast_ratio, pick_theme, theme_head_html

PAIRS = [
    ("ink", "bg"),
    ("muted", "bg"),
    ("ink", "surface"),
    ("muted", "surface"),
    ("on_primary", "primary"),
    ("on_primary", "primary_dark"),
    ("on_hero", "hero_bg"),
]


@pytest.mark.parametrize("theme_key", list(THEMES))
@pytest.mark.parametrize("foreground,background", PAIRS)
def test_every_theme_pair_meets_wcag_aa(theme_key, foreground, background):
    tokens = THEMES[theme_key].tokens

    assert contrast_ratio(tokens[foreground], tokens[background]) >= 4.5


@pytest.mark.parametrize(
    "name,primary_type,category,expected",
    [
        ("Taqueria La Flamita Mixe", None, None, "mexicano"),
        ("Tres Birrias huixquilucan", None, None, "mexicano"),
        ("Sakura Roll Huixquilucan", None, None, "oriental"),
        ("LA CABAÑA DEL PEDREGAL", None, None, "general"),
        ("Lo de Juan", "sushi_restaurant", "Restaurante de sushi", "oriental"),
        ("Lo de Juan", "coffee_shop", "Cafetería", "cafe"),
        ("Lo de Juan", "bar", "Bar", "bar"),
        ("Barbacoa El Güero", None, None, "general"),
        ("Tia Chela Clamatos Y Snaks", None, None, "mexicano"),
    ],
)
def test_pick_theme_uses_the_google_category_first_then_the_name(name, primary_type, category, expected):
    assert pick_theme(name, primary_type, category).key == expected


def test_a_place_category_wins_over_a_misleading_name():
    assert pick_theme("Taquería Nippon", "sushi_restaurant", "Restaurante de sushi").key == "oriental"


def test_theme_head_defines_tokens_fonts_and_reduced_motion():
    html = theme_head_html(THEMES["mexicano"])

    assert "--primary:#C2410C" in html
    assert "--on-primary:#FFFFFF" in html
    assert "fonts.googleapis.com/css2" in html
    assert "prefers-reduced-motion" in html
