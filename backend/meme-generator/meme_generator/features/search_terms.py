"""Deterministic, inspectable Chinese scenario aliases for every public card."""
import re

GROUPS = [
    ('开心 快乐 高兴 欢乐 哈哈 大笑 笑死 happy', ('开心','快乐','高兴','哈哈','大笑','欢呼','狂喜','happy')),
    ('晚安 睡觉 困了 好梦 安睡 night', ('晚安','睡觉','困了','好梦','睡了','sleep')),
    ('你好 嗨 哈喽 hello hi 打招呼 问好', ('你好','哈喽','hello','招手','挥手','打招呼')),
    ('谢谢 感谢 多谢 感恩 辛苦了 thank', ('谢谢','感谢','多谢','感恩','thank')),
    ('早安 早上好 morning 起床', ('早安','早上好','起床')),
    ('再见 拜拜 回头见 bye 告别', ('再见','拜拜','告别','bye')),
    ('好的 收到 明白 没问题 OK 同意', ('好的','收到','明白','没问题','ok','同意')),
    ('加油 努力 冲鸭 鼓励 支持', ('加油','冲鸭','努力','鼓励','支持')),
    ('对不起 抱歉 不好意思 道歉 sorry', ('对不起','抱歉','不好意思','道歉','sorry')),
    ('疑惑 问号 什么 怎么回事 不懂 为啥', ('疑惑','问号','什么','怎么回事','不懂','质疑')),
    ('生气 愤怒 气死了 怒了 angry', ('生气','愤怒','气死','怒了','angry')),
    ('难过 伤心 委屈 哭哭 sad', ('难过','伤心','委屈','哭','sad')),
    ('无语 无奈 尴尬 笑不出来 沉默', ('无语','无奈','尴尬','笑不出来','沉默','awkward')),
    ('可爱 卖萌 萌萌 撒娇', ('可爱','卖萌','撒娇','揉脸','小奶')),
    ('上班 打工 工作 摸鱼 加班', ('上班','打工','工作','摸鱼','加班','代码')),
    ('爱你 喜欢 比心 亲亲 心动 love', ('爱你','喜欢','比心','亲亲','心动','love')),
    ('吃饭 干饭 饿了 美食', ('吃饭','干饭','饿','美食')),
    ('猫咪 猫猫 喵 cat', ('猫','cat')),
    ('小狗 狗狗 汪 dog', ('狗','dog','汪')),
    ('熊猫 panda', ('熊猫','panda')),
]


def keywords(metadata, originals=()):
    name=str(metadata.get('name',''))
    captions=metadata.get('default_texts') or []
    base=[name,*originals,*(metadata.get('keywords') or []),*captions]
    # Captions are evidence; English coarse sentiment tags cannot override a
    # negation such as 笑不出来 / 不开心 / 不喜欢.
    evidence=' '.join(map(str,base)).lower()
    negative=any(s in evidence for s in ('笑不出来','不开心','不高兴','不快乐','不喜欢','不爱'))
    aliases=[]
    for words,signals in GROUPS:
        if negative and words.startswith(('开心','爱你')):continue
        if any(signal in evidence for signal in signals):aliases.extend(words.split())
    tokens=re.findall(r'[a-zA-Z]{2,}|[\u4e00-\u9fff]{2,12}',str(metadata.get('category','')))
    return list(dict.fromkeys(str(v).strip()[:80] for v in [*base,*aliases,*tokens] if str(v).strip()))[:64]
