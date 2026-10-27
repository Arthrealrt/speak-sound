import unittest
from speak_sound.glossary import GameGlossary


class GlossaryTests(unittest.TestCase):
    def setUp(self):
        self.g = GameGlossary()

    def test_gaming_meanings_not_literal_mistranslations(self):
        self.assertEqual(self.g.translate('リロード中', 'ja', 'zh'), '正在换弹。')
        self.assertEqual(self.g.translate("I'm down. Help me.", 'en', 'zh'), '我倒了。救我。')
        self.assertEqual(self.g.translate('队友在右边', 'zh', 'en'), 'Teammate on the right.')
        self.assertEqual(self.g.translate('敌人在右边', 'zh', 'ja'), '敵が右にいる。')

    def test_negation_and_two_clauses_survive_in_both_directions(self):
        self.assertEqual(self.g.translate("No enemies. Don't shoot.", 'en', 'zh'), '没有敌人。别开枪。')
        self.assertEqual(self.g.translate('敵はいない。撃たないで。', 'ja', 'zh'), '没有敌人。别开枪。')
        self.assertEqual(self.g.translate('没有敌人，别开枪', 'zh', 'en'), "No enemies. Don't shoot.")

    def test_never_replaces_substrings_or_drops_distances_or_unknown_context(self):
        for text in ('右边没有敌人', '敌人在右边三百米', '我倒了一个', '可能是右边有人', '敌人在右边，别冲过去'):
            self.assertIsNone(self.g.translate(text, 'zh', 'en'), text)
        self.assertIsNone(self.g.translate("I'm not down", 'en', 'zh'))
        self.assertIsNone(self.g.translate('右に敵はいない', 'ja', 'zh'))

    def test_punctuation_case_and_apostrophes(self):
        self.assertEqual(self.g.translate('I’M DOWN!', 'en', 'zh'), '我倒了。')
        self.assertEqual(self.g.translate('リロード中！', 'ja', 'en'), 'Reloading.')
