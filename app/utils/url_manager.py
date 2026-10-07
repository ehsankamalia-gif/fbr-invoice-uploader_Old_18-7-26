import json
import os

from app.core.paths import data_dir

class UrlManager:
    CONFIG_FILE = "portal_config.json"
    DEFAULT_URL = "https://dealers.ahlportal.com"

    def __init__(self):
        # data_dir(), not os.getcwd(): an installed app's cwd can be its
        # install directory (e.g. C:\Program Files\EhsanTraderFBR), which a
        # non-admin process can't write to - save_default_url() would fail
        # silently there (caught by its bare except), so a saved preference
        # never actually persisted.
        self.config_path = os.path.join(str(data_dir()), self.CONFIG_FILE)

    def get_default_url(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    return data.get('url', self.DEFAULT_URL)
            except Exception:
                pass
        return self.DEFAULT_URL

    def save_default_url(self, url):
        try:
            with open(self.config_path, 'w') as f:
                json.dump({'url': url}, f)
            return True
        except Exception:
            return False

    def save_as_shortcut(self, url, filename):
        """Creates a .url internet shortcut file."""
        try:
            with open(filename, 'w') as f:
                f.write('[InternetShortcut]\n')
                f.write(f'URL={url}\n')
            return True
        except Exception as e:
            raise e
