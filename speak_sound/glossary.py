"""Exact game callouts only: never replace substrings, directions or negations."""
import json
from pathlib import Path
import re
import unicodedata


def normalize(text, language):
    text = unicodedata.normalize('NFKC', text).casefold().replace('’', "'")
    if language == 'en':
        text = text.replace("'", '')
        return ' '.join(re.sub(r'[^\w\s]', ' ', text).split())
    return re.sub(r'[\W_]+', '', text)


class GameGlossary:
    def __init__(self, path=None):
        rows = json.loads((Path(path) if path else Path(__file__).parent / 'assets/callouts.json').read_text(encoding='utf-8'))
        self.entries = {}
        for row in rows:
            for language in ('zh', 'ja', 'en'):
                for variant in row[language]:
                    key = (language, normalize(variant, language))
                    if key in self.entries:
                        raise ValueError(f'重复游戏短句：{language} {variant}')
                    self.entries[key] = row

    def translate(self, text, source, target):
        if source == target:
            return text
        row = self.entries.get((source, normalize(text, source)))
        if row:
            return row[target][0]
        clauses = [part.strip() for part in re.split(r'[，,、。.!！?？;；\n]+', text) if part.strip()]
        if len(clauses) < 2:
            return None
        rows = [self.entries.get((source, normalize(part, source))) for part in clauses]
        if any(row is None for row in rows):
            return None  # Keep full context for the model if any clause is unknown.
        return (' ' if target == 'en' else '').join(row[target][0] for row in rows)
