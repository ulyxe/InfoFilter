import googleapiclient.discovery


def fetch_playlist_ids(playlist_id: str, api_key: str) -> list[str]:
    """
    Fetch all video IDs from a YouTube playlist.

    Args:
        playlist_id: The YouTube playlist ID (e.g., "PLxxxxx")
        api_key: YouTube Data API v3 key

    Returns:
        List of video IDs (strings) in the playlist, in order.

    Raises:
        Any exception raised by the YouTube API client (network errors, auth, etc.)
    """
    youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)

    video_ids = []
    next_page_token = None

    while True:
        params = {"playlistId": playlist_id, "part": "snippet", "maxResults": 50}
        if next_page_token:
            params["pageToken"] = next_page_token
        response = youtube.playlistItems().list(**params).execute()

        # Extract video IDs from this page
        for item in response.get("items", []):
            video_id = item["snippet"]["resourceId"]["videoId"]
            video_ids.append(video_id)

        # Check if there are more pages
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return video_ids
