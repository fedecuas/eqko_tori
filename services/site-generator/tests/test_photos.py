import httpx

from site_generator.photos import GooglePlacesPhotosProvider, photo_media_url

PLACE_BODY = {
    "googleMapsUri": "https://maps.google.com/?cid=1",
    "photos": [
        {
            "name": f"places/p1/photos/REF{i}",
            "googleMapsUri": f"https://www.google.com/maps/photo/{i}",
            "authorAttributions": [
                {"displayName": f"Autor {i}", "uri": f"https://maps.google.com/contrib/{i}", "photoUri": f"https://lh3.googleusercontent.com/a/{i}"}
            ],
        }
        for i in range(5)
    ],
}


def _provider(handler, max_photos=3):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GooglePlacesPhotosProvider(api_key="server-key", max_photos=max_photos, client=client)


def test_fetch_parses_photos_attribution_and_place_uri_limited_to_max_photos():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        return httpx.Response(200, json=PLACE_BODY)

    media = _provider(handler).fetch("p1")

    assert seen["url"] == "https://places.googleapis.com/v1/places/p1"
    assert seen["headers"]["x-goog-api-key"] == "server-key"
    assert seen["headers"]["x-goog-fieldmask"] == "photos,googleMapsUri"
    assert len(media.photos) == 3
    assert media.photos[0].name == "places/p1/photos/REF0"
    assert media.photos[0].attributions[0].display_name == "Autor 0"
    assert media.photos[0].google_maps_uri == "https://www.google.com/maps/photo/0"
    assert media.google_maps_uri == "https://maps.google.com/?cid=1"


def test_fetch_returns_no_photos_when_the_place_has_none():
    media = _provider(lambda request: httpx.Response(200, json={})).fetch("p1")

    assert media.photos == ()


def test_fetch_degrades_to_no_photos_on_http_error_instead_of_raising():
    media = _provider(lambda request: httpx.Response(403, json={"error": "denied"})).fetch("p1")

    assert media.photos == ()
    assert media.google_maps_uri is None


def test_photo_media_url_points_straight_at_google_with_the_public_key():
    url = photo_media_url("places/p1/photos/REF0", "pub key&x")

    assert url.startswith("https://places.googleapis.com/v1/places/p1/photos/REF0/media?")
    assert "maxWidthPx=800" in url
    assert "key=pub%20key%26x" in url
