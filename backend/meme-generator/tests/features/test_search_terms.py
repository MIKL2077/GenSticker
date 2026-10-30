import unittest

from meme_generator.features.search_terms import keywords


class SearchTermsTests(unittest.TestCase):
    def test_subject_action_and_scenario_aliases(self):
        words = keywords({'name': '柴犬摇摆打工', 'tags': ['动图']})
        for value in ['狗狗', 'doge', '蹦迪', '社畜', '职场']:
            self.assertIn(value, words)
        self.assertIn('哈基米', keywords({'name': '白猫扭头'}))
        self.assertIn('ikun', keywords({'name': '蔡徐坤开心'}))
        self.assertIn('ASCII', keywords({'name':'字符画'}))
        self.assertIn('音游', keywords({'name':'旅行伙伴觉醒'}))
        self.assertIn('哈基米', keywords({'name':'新反应','category':'027Cat_猫BQB'}))

    def test_negated_emotions_and_ascii_word_boundaries(self):
        for name, unwanted in [('不开心', '快乐'), ('不喜欢上班', '表白'),
                               ('笑不出来', 'happy'), ('别哭', '伤心'),
                               ('不同意', '好的')]:
            self.assertNotIn(unwanted, keywords({'name': name}))
        self.assertIn('安慰', keywords({'name': '别哭'}))
        self.assertNotIn('猫咪', keywords({'name': 'education'}))
        self.assertNotIn('猫咪', keywords({'name': '熊猫头摇摆'}))
        self.assertIn('猫咪', keywords({'name': 'cat_dance'}))

    def test_metadata_does_not_recursively_expand_generated_aliases(self):
        first = keywords({'name': '小狗工作'})
        second = keywords({'name': '小狗工作', 'keywords': first})
        self.assertEqual(first, second)
        self.assertEqual(first, keywords({'name':'小狗工作','keywords':first}, first))
        self.assertNotIn('熬夜', first)
        self.assertIn('自定义暗号', keywords({'name': '测试', 'keywords': ['自定义暗号']}))
        self.assertNotIn('猫咪', keywords({'name':'熊猫头','keywords':['猫咪','cat']}))

    def test_cat_actions_and_chat_intent_without_inventing_a_wink(self):
        cases = [
            ('白猫打哈欠', ['犯困', 'yawning']),
            ('黑猫被摸头后眨眨眼', ['blinking', '眨眼']),
            ('奶牛猫满脸写着不耐烦', ['烦躁', 'annoyed']),
            ('灰猫欲言又止', ['话到嘴边', '说不出口']),
            ('小猫等你回复', ['等消息', '已读不回']),
            ('橘猫心满意足眯眼笑', ['舒服', '惬意', 'squint']),
            ('猫咪嘴巴合不上', ['张嘴', 'open-mouth']),
        ]
        for name, expected in cases:
            words = keywords({'name': name})
            for word in expected:
                self.assertIn(word, words, name)
            self.assertEqual(words, keywords({'name': name, 'keywords': words}))
        self.assertNotIn('抛媚眼', keywords({'name': '猫咪眨眼'}))
        self.assertNotIn('睁大眼', keywords({'name': '猫咪闭眼休息'}))
        self.assertIn('抛媚眼', keywords({'name': 'cat wink'}))
        self.assertNotIn('yawning', keywords({'name': 'scaryawn'}))

    def test_normalized_bounded_and_tolerates_legacy_values(self):
        result = keywords({'name': 'ＯＫ', 'keywords': ['ok', 'ＯＫ', None, 5],
                           'default_texts': None, 'tags': '工作'})
        self.assertEqual(sum(x.casefold() == 'ok' for x in result), 1)
        self.assertIn('收到', result)
        self.assertIn('社畜', result)
        result = keywords({'name': '测试', 'keywords': ['x' * 200 + str(i) for i in range(1000)]})
        self.assertLessEqual(len(result), 128)
        self.assertTrue(all(len(x) <= 80 for x in result))


if __name__ == '__main__':
    unittest.main()
