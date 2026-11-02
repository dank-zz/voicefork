import json
import locale
import os
from tools.file_io import read_text


_LOCALE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")  # voicefork: module-relative


def load_language_list(language):
    return json.loads(read_text(os.path.join(_LOCALE, f"{language}.json")))


class I18nAuto:
    def __init__(self, language=None):
        language = "en_US"  # voicefork: only English is shipped
        self.language = language
        self.language_map = load_language_list(language)

    def __call__(self, key):
        return self.language_map.get(key, key)

    def __repr__(self):
        return "Use Language: " + self.language
