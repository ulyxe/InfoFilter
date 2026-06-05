import pytest
import yt_fetcher


class MockResource:
    """Mock YouTube API resource."""
    def __init__(self, request):
        self.request = request

    def execute(self):
        return self.request()


class MockPlaylistItems:
    """Mock playlistItems() resource."""
    def __init__(self, response_gen):
        self.response_gen = response_gen
        self.call_count = 0

    def list(self, **kwargs):
        """Return a mock request that generates responses."""
        call_index = self.call_count
        self.call_count += 1
        return MockResource(lambda: self.response_gen(call_index, kwargs))


class MockYoutubeClient:
    """Mock YouTube API client."""
    def __init__(self, response_gen):
        self.playlist_items = MockPlaylistItems(response_gen)

    def playlistItems(self):
        return self.playlist_items


def test_fetch_playlist_ids_empty_playlist(monkeypatch):
    """Test fetching from an empty playlist."""
    def mock_build(service, version, developerKey):
        def response_gen(call_index, kwargs):
            return {"items": []}
        return MockYoutubeClient(response_gen)

    monkeypatch.setattr(yt_fetcher.googleapiclient.discovery, "build", mock_build)

    result = yt_fetcher.fetch_playlist_ids("PLxxx", "test_key")
    assert result == []


def test_fetch_playlist_ids_single_page(monkeypatch):
    """Test fetching a playlist that fits on one page."""
    def mock_build(service, version, developerKey):
        def response_gen(call_index, kwargs):
            return {
                "items": [
                    {"snippet": {"resourceId": {"videoId": "vid1"}}},
                    {"snippet": {"resourceId": {"videoId": "vid2"}}},
                    {"snippet": {"resourceId": {"videoId": "vid3"}}},
                ]
            }
        return MockYoutubeClient(response_gen)

    monkeypatch.setattr(yt_fetcher.googleapiclient.discovery, "build", mock_build)

    result = yt_fetcher.fetch_playlist_ids("PLxxx", "test_key")
    assert result == ["vid1", "vid2", "vid3"]


def test_fetch_playlist_ids_multi_page(monkeypatch):
    """Test fetching a playlist that spans multiple pages."""
    def mock_build(service, version, developerKey):
        def response_gen(call_index, kwargs):
            if call_index == 0:
                return {
                    "items": [
                        {"snippet": {"resourceId": {"videoId": "vid1"}}},
                        {"snippet": {"resourceId": {"videoId": "vid2"}}},
                    ],
                    "nextPageToken": "page2"
                }
            elif call_index == 1:
                return {
                    "items": [
                        {"snippet": {"resourceId": {"videoId": "vid3"}}},
                        {"snippet": {"resourceId": {"videoId": "vid4"}}},
                    ],
                    "nextPageToken": "page3"
                }
            else:  # call_index == 2
                return {
                    "items": [
                        {"snippet": {"resourceId": {"videoId": "vid5"}}},
                    ]
                }
        return MockYoutubeClient(response_gen)

    monkeypatch.setattr(yt_fetcher.googleapiclient.discovery, "build", mock_build)

    result = yt_fetcher.fetch_playlist_ids("PLxxx", "test_key")
    assert result == ["vid1", "vid2", "vid3", "vid4", "vid5"]


def test_fetch_playlist_ids_api_error_raises(monkeypatch):
    """Test that API errors are raised to the caller."""
    def mock_build(service, version, developerKey):
        def response_gen(call_index, kwargs):
            raise ValueError("API error: unauthorized")
        return MockYoutubeClient(response_gen)

    monkeypatch.setattr(yt_fetcher.googleapiclient.discovery, "build", mock_build)

    with pytest.raises(ValueError, match="API error"):
        yt_fetcher.fetch_playlist_ids("PLxxx", "test_key")


def test_fetch_playlist_ids_passes_correct_params(monkeypatch):
    """Test that the correct parameters are passed to the API."""
    captured_kwargs = {}

    def mock_build(service, version, developerKey):
        def response_gen(call_index, kwargs):
            captured_kwargs.update(kwargs)
            return {"items": []}
        return MockYoutubeClient(response_gen)

    monkeypatch.setattr(yt_fetcher.googleapiclient.discovery, "build", mock_build)

    yt_fetcher.fetch_playlist_ids("PLtest123", "key_abc")

    assert captured_kwargs["playlistId"] == "PLtest123"
    assert captured_kwargs["part"] == "snippet"
    assert captured_kwargs["maxResults"] == 50
