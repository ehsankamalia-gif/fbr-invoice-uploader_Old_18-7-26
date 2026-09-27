import logging
from typing import Optional, Dict, Any, List

import requests

from .version_manager import VersionManager

logger = logging.getLogger(__name__)

GITHUB_API_VERSION = "2022-11-28"


class UpdateCheckError(Exception):
    """Raised when the update check itself could not be completed - a
    network problem, an auth/permission failure, a repo with no releases
    yet, or a release that's missing the fields the updater needs. This is
    deliberately a distinct type from "checked successfully, no update
    available" (which is simply a return value of None), so the caller
    (UpdaterManager) can tell the two apart and never report a failed
    check as if it were a reassuring "you're up to date" - the mixing of
    those two cases was the actual, reported bug the whole system had
    when it checked a (broken) Bitbucket URL: every failure was silently
    reported as SUCCESS."""


class UpdateChecker:
    """
    Checks a GitHub repository's Releases for a newer version than the one
    currently installed. Uses the public GitHub REST API - no auth needed
    for a public repo; pass a token for a private one.
    """

    def __init__(self, repo: str, token: Optional[str] = None):
        """
        Args:
            repo: "owner/repo", e.g. "ehsankamalia-gif/fbr-invoice-uploader_Old_18-7-26"
            token: Optional GitHub Personal Access Token, only needed if
                   `repo` is private.
        """
        self.repo = repo
        self.token = token or None

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def _find_installer_asset(assets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return next((a for a in assets if str(a.get("name", "")).lower().endswith(".exe")), None)

    @staticmethod
    def _find_checksum(assets: List[Dict[str, Any]], installer_asset: Dict[str, Any]) -> Optional[str]:
        """Looks for a SHA-256 for the installer, in order of preference:
        1. GitHub's own asset `digest` field (present on newer uploads),
        2. a sidecar "<installer-name>.sha256" asset,
        3. a shared "checksums.txt" listing multiple files.
        Returns None (not an error) if no checksum is published anywhere -
        older/simpler releases just won't get integrity verification,
        rather than being blocked outright."""
        digest = installer_asset.get("digest")
        if digest and digest.startswith("sha256:"):
            return digest.split(":", 1)[1].strip().lower()

        installer_name = installer_asset.get("name", "")
        sidecar = next((a for a in assets if a.get("name") == f"{installer_name}.sha256"), None)
        if sidecar:
            try:
                resp = requests.get(sidecar["browser_download_url"], timeout=10)
                resp.raise_for_status()
                return resp.text.strip().split()[0].lower()
            except Exception as e:
                logger.warning(f"Found a .sha256 asset but could not read it: {e}")
                return None

        checksums_file = next((a for a in assets if str(a.get("name", "")).lower() == "checksums.txt"), None)
        if checksums_file:
            try:
                resp = requests.get(checksums_file["browser_download_url"], timeout=10)
                resp.raise_for_status()
                for line in resp.text.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[-1].lstrip("*") == installer_name:
                        return parts[0].lower()
            except Exception as e:
                logger.warning(f"Found checksums.txt but could not read it: {e}")
                return None

        return None

    def fetch_latest_release(self, timeout: int = 15) -> Optional[Dict[str, Any]]:
        """Fetches and validates the latest GitHub release. Returns None if
        the repo simply has no releases published yet - GitHub's own,
        well-defined meaning for a 404 on this specific endpoint, and a
        perfectly normal state before the very first release exists (not
        an error to alarm the user with on every startup). Raises
        UpdateCheckError for anything else that goes wrong - a genuine
        network problem, an HTTP error other than "no releases yet", or a
        release that's missing what the updater needs - so THOSE failures
        can never be mistaken for "no update available", which was the
        actual, reported bug: every failure, for any reason, used to be
        silently reported as success."""
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        try:
            response = requests.get(url, headers=self._headers(), timeout=timeout, verify=True)
        except requests.exceptions.RequestException as e:
            raise UpdateCheckError(f"Could not reach GitHub: {e}") from e

        if response.status_code == 404:
            logger.info(f"No releases published yet for '{self.repo}' - nothing to update to.")
            return None
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise UpdateCheckError(f"GitHub returned an error ({response.status_code}): {e}") from e

        try:
            data = response.json()
        except ValueError as e:
            raise UpdateCheckError(f"GitHub returned an unreadable response: {e}") from e

        tag = data.get("tag_name")
        if not tag:
            raise UpdateCheckError("Latest GitHub release has no tag_name.")

        assets = data.get("assets") or []
        installer_asset = self._find_installer_asset(assets)
        if not installer_asset:
            raise UpdateCheckError(
                f"Latest release '{tag}' has no .exe installer attached as a release asset."
            )

        return {
            "latest_version": tag.lstrip("vV"),
            "download_url": installer_asset["browser_download_url"],
            "asset_name": installer_asset.get("name"),
            "asset_size": installer_asset.get("size"),
            "sha256": self._find_checksum(assets, installer_asset),
            "changelog": (data.get("body") or "").strip() or "No changelog provided.",
            "release_date": (data.get("published_at") or "")[:10],
            "release_url": data.get("html_url"),
        }

    def check_for_update(self, current_version: str) -> Optional[Dict[str, Any]]:
        """Returns the latest release's info if it's newer than
        `current_version`, else None (also None if no releases have been
        published yet). Raises UpdateCheckError if the check itself could
        not be completed - see fetch_latest_release."""
        latest_info = self.fetch_latest_release()
        if latest_info is None:
            return None
        if VersionManager.is_update_available(current_version, latest_info["latest_version"]):
            return latest_info
        return None
