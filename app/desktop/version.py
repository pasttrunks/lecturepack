"""Single source of truth for the app version and update channel.

The release workflow (.github/workflows/release.yml) checks that the pushed
tag matches __version__ before building, so bump this first, then tag.
"""

__version__ = "1.0.0"

# GitHub repository that hosts releases for the auto-updater ("owner/repo").
GITHUB_REPO = "pasttrunks/lecturepack"

APP_NAME = "LecturePack"
ORG_NAME = "LecturePack"
