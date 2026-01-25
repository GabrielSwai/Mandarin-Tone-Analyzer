from flask import Blueprint, send_from_directory, request, jsonify, url_for, current_app
from pathlib import Path
from werkzeug.utils import secure_filename
from uuid import uuid4
from sqlalchemy import select, func
from mainapp.db import get_session
from mainapp.models import Phrase, Attempt
from urllib.parse import urlparse
from openai import OpenAI
import random # for random phrase selection
import json # for writing phrase_id sidecar metadata
import time # for simple timestamps
import os
import re
import subprocess
import numpy as np
import parselmouth
import matplotlib
matplotlib.use("Agg") # force non-GUI backend so plots work inside Flask threads
import matplotlib.pyplot as plt

apiapp = Blueprint("apiroutes", __name__)
client = OpenAI() # OpenAI client reads OPENAI_API_KEY from .env

TTS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "tts" # where generated TTS files are stored
TTS_DIR.mkdir(parents = True, exist_ok = True) # ensure dir exists
ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" # where plots + wavs go
ARTIFACT_DIR.mkdir(exist_ok = True) # ensure artifacts dir exists
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads" # path of upload directory
UPLOAD_DIR.mkdir(exist_ok = True) # check that upload dir exists
PHRASES = [  # 300 common phrases (2–5 syllables); from ChatGPT
    {"phrase_id": "p001", "hanzi": "你好", "pinyin": "nǐ hǎo"},
    {"phrase_id": "p002", "hanzi": "谢谢", "pinyin": "xiè xie"},
    {"phrase_id": "p003", "hanzi": "不客气", "pinyin": "bú kè qì"},
    {"phrase_id": "p004", "hanzi": "对不起", "pinyin": "duì bù qǐ"},
    {"phrase_id": "p005", "hanzi": "没关系", "pinyin": "méi guān xì"},
    {"phrase_id": "p006", "hanzi": "再见", "pinyin": "zài jiàn"},
    {"phrase_id": "p007", "hanzi": "早上好", "pinyin": "zǎo shang hǎo"},
    {"phrase_id": "p008", "hanzi": "晚上好", "pinyin": "wǎn shang hǎo"},
    {"phrase_id": "p009", "hanzi": "中午好", "pinyin": "zhōng wǔ hǎo"},
    {"phrase_id": "p010", "hanzi": "你好吗", "pinyin": "nǐ hǎo ma"},
    {"phrase_id": "p011", "hanzi": "我很好", "pinyin": "wǒ hěn hǎo"},
    {"phrase_id": "p012", "hanzi": "还不错", "pinyin": "hái bú cuò"},
    {"phrase_id": "p013", "hanzi": "你呢", "pinyin": "nǐ ne"},
    {"phrase_id": "p014", "hanzi": "太好了", "pinyin": "tài hǎo le"},
    {"phrase_id": "p015", "hanzi": "太棒了", "pinyin": "tài bàng le"},
    {"phrase_id": "p016", "hanzi": "没问题", "pinyin": "méi wèn tí"},
    {"phrase_id": "p017", "hanzi": "可以吗", "pinyin": "kě yǐ ma"},
    {"phrase_id": "p018", "hanzi": "可以", "pinyin": "kě yǐ"},
    {"phrase_id": "p019", "hanzi": "不可以", "pinyin": "bù kě yǐ"},
    {"phrase_id": "p020", "hanzi": "当然", "pinyin": "dāng rán"},
    {"phrase_id": "p021", "hanzi": "没事", "pinyin": "méi shì"},
    {"phrase_id": "p022", "hanzi": "真的", "pinyin": "zhēn de"},
    {"phrase_id": "p023", "hanzi": "是吗", "pinyin": "shì ma"},
    {"phrase_id": "p024", "hanzi": "不是", "pinyin": "bú shì"},
    {"phrase_id": "p025", "hanzi": "是的", "pinyin": "shì de"},
    {"phrase_id": "p026", "hanzi": "好的", "pinyin": "hǎo de"},
    {"phrase_id": "p027", "hanzi": "好吧", "pinyin": "hǎo ba"},
    {"phrase_id": "p028", "hanzi": "等等我", "pinyin": "děng děng wǒ"},
    {"phrase_id": "p029", "hanzi": "快点", "pinyin": "kuài diǎn"},
    {"phrase_id": "p030", "hanzi": "慢一点", "pinyin": "màn yì diǎn"},
    {"phrase_id": "p031", "hanzi": "别着急", "pinyin": "bié zháo jí"},
    {"phrase_id": "p032", "hanzi": "没时间", "pinyin": "méi shí jiān"},
    {"phrase_id": "p033", "hanzi": "有时间", "pinyin": "yǒu shí jiān"},
    {"phrase_id": "p034", "hanzi": "我不知道", "pinyin": "wǒ bù zhī dào"},
    {"phrase_id": "p035", "hanzi": "我明白", "pinyin": "wǒ míng bái"},
    {"phrase_id": "p036", "hanzi": "我懂了", "pinyin": "wǒ dǒng le"},
    {"phrase_id": "p037", "hanzi": "听不懂", "pinyin": "tīng bù dǒng"},
    {"phrase_id": "p038", "hanzi": "看不懂", "pinyin": "kàn bù dǒng"},
    {"phrase_id": "p039", "hanzi": "再说一遍", "pinyin": "zài shuō yí biàn"},
    {"phrase_id": "p040", "hanzi": "慢慢说", "pinyin": "màn màn shuō"},
    {"phrase_id": "p041", "hanzi": "你说什么", "pinyin": "nǐ shuō shén me"},
    {"phrase_id": "p042", "hanzi": "什么意思", "pinyin": "shén me yì si"},
    {"phrase_id": "p043", "hanzi": "我不懂", "pinyin": "wǒ bù dǒng"},
    {"phrase_id": "p044", "hanzi": "我会说", "pinyin": "wǒ huì shuō"},
    {"phrase_id": "p045", "hanzi": "我会写", "pinyin": "wǒ huì xiě"},
    {"phrase_id": "p046", "hanzi": "你会吗", "pinyin": "nǐ huì ma"},
    {"phrase_id": "p047", "hanzi": "你会说吗", "pinyin": "nǐ huì shuō ma"},
    {"phrase_id": "p048", "hanzi": "你会写吗", "pinyin": "nǐ huì xiě ma"},
    {"phrase_id": "p049", "hanzi": "我在学习", "pinyin": "wǒ zài xué xí"},
    {"phrase_id": "p050", "hanzi": "我在工作", "pinyin": "wǒ zài gōng zuò"},
    {"phrase_id": "p051", "hanzi": "你忙吗", "pinyin": "nǐ máng ma"},
    {"phrase_id": "p052", "hanzi": "我很忙", "pinyin": "wǒ hěn máng"},
    {"phrase_id": "p053", "hanzi": "不太忙", "pinyin": "bú tài máng"},
    {"phrase_id": "p054", "hanzi": "辛苦了", "pinyin": "xīn kǔ le"},
    {"phrase_id": "p055", "hanzi": "加油", "pinyin": "jiā yóu"},
    {"phrase_id": "p056", "hanzi": "没办法", "pinyin": "méi bàn fǎ"},
    {"phrase_id": "p057", "hanzi": "太贵了", "pinyin": "tài guì le"},
    {"phrase_id": "p058", "hanzi": "便宜一点", "pinyin": "pián yí yì diǎn"},
    {"phrase_id": "p059", "hanzi": "多少钱", "pinyin": "duō shǎo qián"},
    {"phrase_id": "p060", "hanzi": "我买这个", "pinyin": "wǒ mǎi zhè ge"},
    {"phrase_id": "p061", "hanzi": "我不要", "pinyin": "wǒ bú yào"},
    {"phrase_id": "p062", "hanzi": "我要这个", "pinyin": "wǒ yào zhè ge"},
    {"phrase_id": "p063", "hanzi": "我想要", "pinyin": "wǒ xiǎng yào"},
    {"phrase_id": "p064", "hanzi": "我想去", "pinyin": "wǒ xiǎng qù"},
    {"phrase_id": "p065", "hanzi": "我想看", "pinyin": "wǒ xiǎng kàn"},
    {"phrase_id": "p066", "hanzi": "我想吃", "pinyin": "wǒ xiǎng chī"},
    {"phrase_id": "p067", "hanzi": "我想喝", "pinyin": "wǒ xiǎng hē"},
    {"phrase_id": "p068", "hanzi": "我饿了", "pinyin": "wǒ è le"},
    {"phrase_id": "p069", "hanzi": "我渴了", "pinyin": "wǒ kě le"},
    {"phrase_id": "p070", "hanzi": "我累了", "pinyin": "wǒ lèi le"},
    {"phrase_id": "p071", "hanzi": "我困了", "pinyin": "wǒ kùn le"},
    {"phrase_id": "p072", "hanzi": "我生病了", "pinyin": "wǒ shēng bìng le"},
    {"phrase_id": "p073", "hanzi": "不舒服", "pinyin": "bù shū fu"},
    {"phrase_id": "p074", "hanzi": "头疼", "pinyin": "tóu téng"},
    {"phrase_id": "p075", "hanzi": "肚子疼", "pinyin": "dù zi téng"},
    {"phrase_id": "p076", "hanzi": "发烧了", "pinyin": "fā shāo le"},
    {"phrase_id": "p077", "hanzi": "我没事", "pinyin": "wǒ méi shì"},
    {"phrase_id": "p078", "hanzi": "小心点", "pinyin": "xiǎo xīn diǎn"},
    {"phrase_id": "p079", "hanzi": "没关系的", "pinyin": "méi guān xì de"},
    {"phrase_id": "p080", "hanzi": "太可爱了", "pinyin": "tài kě ài le"},
    {"phrase_id": "p081", "hanzi": "太帅了", "pinyin": "tài shuài le"},
    {"phrase_id": "p082", "hanzi": "太漂亮了", "pinyin": "tài piào liang le"},
    {"phrase_id": "p083", "hanzi": "真厉害", "pinyin": "zhēn lì hài"},
    {"phrase_id": "p084", "hanzi": "太难了", "pinyin": "tài nán le"},
    {"phrase_id": "p085", "hanzi": "不难", "pinyin": "bù nán"},
    {"phrase_id": "p086", "hanzi": "很容易", "pinyin": "hěn róng yì"},
    {"phrase_id": "p087", "hanzi": "我喜欢", "pinyin": "wǒ xǐ huān"},
    {"phrase_id": "p088", "hanzi": "我不喜欢", "pinyin": "wǒ bù xǐ huān"},
    {"phrase_id": "p089", "hanzi": "你喜欢吗", "pinyin": "nǐ xǐ huān ma"},
    {"phrase_id": "p090", "hanzi": "我爱你", "pinyin": "wǒ ài nǐ"},
    {"phrase_id": "p091", "hanzi": "我想你", "pinyin": "wǒ xiǎng nǐ"},
    {"phrase_id": "p092", "hanzi": "开心一点", "pinyin": "kāi xīn yì diǎn"},
    {"phrase_id": "p093", "hanzi": "别难过", "pinyin": "bié nán guò"},
    {"phrase_id": "p094", "hanzi": "别担心", "pinyin": "bié dān xīn"},
    {"phrase_id": "p095", "hanzi": "我很高兴", "pinyin": "wǒ hěn gāo xìng"},
    {"phrase_id": "p096", "hanzi": "我很开心", "pinyin": "wǒ hěn kāi xīn"},
    {"phrase_id": "p097", "hanzi": "我很紧张", "pinyin": "wǒ hěn jǐn zhāng"},
    {"phrase_id": "p098", "hanzi": "我有点怕", "pinyin": "wǒ yǒu diǎn pà"},
    {"phrase_id": "p099", "hanzi": "太尴尬了", "pinyin": "tài gān gà le"},
    {"phrase_id": "p100", "hanzi": "真好玩", "pinyin": "zhēn hǎo wán"},
    {"phrase_id": "p101", "hanzi": "好无聊", "pinyin": "hǎo wú liáo"},
    {"phrase_id": "p102", "hanzi": "好好吃", "pinyin": "hǎo hǎo chī"},
    {"phrase_id": "p103", "hanzi": "好喝吗", "pinyin": "hǎo hē ma"},
    {"phrase_id": "p104", "hanzi": "很好喝", "pinyin": "hěn hǎo hē"},
    {"phrase_id": "p105", "hanzi": "太辣了", "pinyin": "tài là le"},
    {"phrase_id": "p106", "hanzi": "不太辣", "pinyin": "bú tài là"},
    {"phrase_id": "p107", "hanzi": "太甜了", "pinyin": "tài tián le"},
    {"phrase_id": "p108", "hanzi": "太咸了", "pinyin": "tài xián le"},
    {"phrase_id": "p109", "hanzi": "少放盐", "pinyin": "shǎo fàng yán"},
    {"phrase_id": "p110", "hanzi": "别放辣", "pinyin": "bié fàng là"},
    {"phrase_id": "p111", "hanzi": "来一份", "pinyin": "lái yí fèn"},
    {"phrase_id": "p112", "hanzi": "来一杯", "pinyin": "lái yì bēi"},
    {"phrase_id": "p113", "hanzi": "再来一个", "pinyin": "zài lái yí ge"},
    {"phrase_id": "p114", "hanzi": "不要了", "pinyin": "bú yào le"},
    {"phrase_id": "p115", "hanzi": "打包带走", "pinyin": "dǎ bāo dài zǒu"},
    {"phrase_id": "p116", "hanzi": "在这吃", "pinyin": "zài zhè chī"},
    {"phrase_id": "p117", "hanzi": "用现金", "pinyin": "yòng xiàn jīn"},
    {"phrase_id": "p118", "hanzi": "刷卡吗", "pinyin": "shuā kǎ ma"},
    {"phrase_id": "p119", "hanzi": "用微信", "pinyin": "yòng wēi xìn"},
    {"phrase_id": "p120", "hanzi": "用支付宝", "pinyin": "yòng zhī fù bǎo"},
    {"phrase_id": "p121", "hanzi": "给你", "pinyin": "gěi nǐ"},
    {"phrase_id": "p122", "hanzi": "给我", "pinyin": "gěi wǒ"},
    {"phrase_id": "p123", "hanzi": "请给我", "pinyin": "qǐng gěi wǒ"},
    {"phrase_id": "p124", "hanzi": "请帮我", "pinyin": "qǐng bāng wǒ"},
    {"phrase_id": "p125", "hanzi": "帮个忙", "pinyin": "bāng ge máng"},
    {"phrase_id": "p126", "hanzi": "麻烦你", "pinyin": "má fan nǐ"},
    {"phrase_id": "p127", "hanzi": "谢谢你", "pinyin": "xiè xie nǐ"},
    {"phrase_id": "p128", "hanzi": "不用谢", "pinyin": "bú yòng xiè"},
    {"phrase_id": "p129", "hanzi": "请进", "pinyin": "qǐng jìn"},
    {"phrase_id": "p130", "hanzi": "请坐", "pinyin": "qǐng zuò"},
    {"phrase_id": "p131", "hanzi": "请稍等", "pinyin": "qǐng shāo děng"},
    {"phrase_id": "p132", "hanzi": "等一下", "pinyin": "děng yí xià"},
    {"phrase_id": "p133", "hanzi": "快一点", "pinyin": "kuài yì diǎn"},
    {"phrase_id": "p134", "hanzi": "慢一点", "pinyin": "màn yì diǎn"},
    {"phrase_id": "p135", "hanzi": "大声点", "pinyin": "dà shēng diǎn"},
    {"phrase_id": "p136", "hanzi": "小声点", "pinyin": "xiǎo shēng diǎn"},
    {"phrase_id": "p137", "hanzi": "听清楚", "pinyin": "tīng qīng chu"},
    {"phrase_id": "p138", "hanzi": "看清楚", "pinyin": "kàn qīng chu"},
    {"phrase_id": "p139", "hanzi": "你说吧", "pinyin": "nǐ shuō ba"},
    {"phrase_id": "p140", "hanzi": "我说完了", "pinyin": "wǒ shuō wán le"},
    {"phrase_id": "p141", "hanzi": "我走了", "pinyin": "wǒ zǒu le"},
    {"phrase_id": "p142", "hanzi": "我来了", "pinyin": "wǒ lái le"},
    {"phrase_id": "p143", "hanzi": "我回家", "pinyin": "wǒ huí jiā"},
    {"phrase_id": "p144", "hanzi": "回头见", "pinyin": "huí tóu jiàn"},
    {"phrase_id": "p145", "hanzi": "明天见", "pinyin": "míng tiān jiàn"},
    {"phrase_id": "p146", "hanzi": "下次见", "pinyin": "xià cì jiàn"},
    {"phrase_id": "p147", "hanzi": "周末见", "pinyin": "zhōu mò jiàn"},
    {"phrase_id": "p148", "hanzi": "生日快乐", "pinyin": "shēng rì kuài lè"},
    {"phrase_id": "p149", "hanzi": "新年快乐", "pinyin": "xīn nián kuài lè"},
    {"phrase_id": "p150", "hanzi": "节日快乐", "pinyin": "jié rì kuài lè"},
    {"phrase_id": "p151", "hanzi": "恭喜你", "pinyin": "gōng xǐ nǐ"},
    {"phrase_id": "p152", "hanzi": "祝你好运", "pinyin": "zhù nǐ hǎo yùn"},
    {"phrase_id": "p153", "hanzi": "一路顺风", "pinyin": "yí lù shùn fēng"},
    {"phrase_id": "p154", "hanzi": "一路平安", "pinyin": "yí lù píng ān"},
    {"phrase_id": "p155", "hanzi": "保重身体", "pinyin": "bǎo zhòng shēn tǐ"},
    {"phrase_id": "p156", "hanzi": "注意安全", "pinyin": "zhù yì ān quán"},
    {"phrase_id": "p157", "hanzi": "注意休息", "pinyin": "zhù yì xiū xi"},
    {"phrase_id": "p158", "hanzi": "早点睡", "pinyin": "zǎo diǎn shuì"},
    {"phrase_id": "p159", "hanzi": "睡个好觉", "pinyin": "shuì ge hǎo jiào"},
    {"phrase_id": "p160", "hanzi": "做个好梦", "pinyin": "zuò ge hǎo mèng"},
    {"phrase_id": "p161", "hanzi": "几点了", "pinyin": "jǐ diǎn le"},
    {"phrase_id": "p162", "hanzi": "现在几点", "pinyin": "xiàn zài jǐ diǎn"},
    {"phrase_id": "p163", "hanzi": "今天几号", "pinyin": "jīn tiān jǐ hào"},
    {"phrase_id": "p164", "hanzi": "今天星期几", "pinyin": "jīn tiān xīng qī jǐ"},
    {"phrase_id": "p165", "hanzi": "明天星期几", "pinyin": "míng tiān xīng qī jǐ"},
    {"phrase_id": "p166", "hanzi": "我迟到了", "pinyin": "wǒ chí dào le"},
    {"phrase_id": "p167", "hanzi": "我快到了", "pinyin": "wǒ kuài dào le"},
    {"phrase_id": "p168", "hanzi": "马上到", "pinyin": "mǎ shàng dào"},
    {"phrase_id": "p169", "hanzi": "再等我", "pinyin": "zài děng wǒ"},
    {"phrase_id": "p170", "hanzi": "别走", "pinyin": "bié zǒu"},
    {"phrase_id": "p171", "hanzi": "去哪儿", "pinyin": "qù nǎr"},
    {"phrase_id": "p172", "hanzi": "你去哪儿", "pinyin": "nǐ qù nǎr"},
    {"phrase_id": "p173", "hanzi": "我去哪儿", "pinyin": "wǒ qù nǎr"},
    {"phrase_id": "p174", "hanzi": "在哪里", "pinyin": "zài nǎ lǐ"},
    {"phrase_id": "p175", "hanzi": "你在哪儿", "pinyin": "nǐ zài nǎr"},
    {"phrase_id": "p176", "hanzi": "我在这儿", "pinyin": "wǒ zài zhèr"},
    {"phrase_id": "p177", "hanzi": "在那边", "pinyin": "zài nà biān"},
    {"phrase_id": "p178", "hanzi": "在这边", "pinyin": "zài zhè biān"},
    {"phrase_id": "p179", "hanzi": "往左走", "pinyin": "wǎng zuǒ zǒu"},
    {"phrase_id": "p180", "hanzi": "往右走", "pinyin": "wǎng yòu zǒu"},
    {"phrase_id": "p181", "hanzi": "直走", "pinyin": "zhí zǒu"},
    {"phrase_id": "p182", "hanzi": "前面", "pinyin": "qián miàn"},
    {"phrase_id": "p183", "hanzi": "后面", "pinyin": "hòu miàn"},
    {"phrase_id": "p184", "hanzi": "左边", "pinyin": "zuǒ biān"},
    {"phrase_id": "p185", "hanzi": "右边", "pinyin": "yòu biān"},
    {"phrase_id": "p186", "hanzi": "附近有吗", "pinyin": "fù jìn yǒu ma"},
    {"phrase_id": "p187", "hanzi": "离这儿近吗", "pinyin": "lí zhèr jìn ma"},
    {"phrase_id": "p188", "hanzi": "怎么走", "pinyin": "zěn me zǒu"},
    {"phrase_id": "p189", "hanzi": "走过去", "pinyin": "zǒu guò qù"},
    {"phrase_id": "p190", "hanzi": "坐地铁", "pinyin": "zuò dì tiě"},
    {"phrase_id": "p191", "hanzi": "坐公交", "pinyin": "zuò gōng jiāo"},
    {"phrase_id": "p192", "hanzi": "打车去", "pinyin": "dǎ chē qù"},
    {"phrase_id": "p193", "hanzi": "到这里", "pinyin": "dào zhè lǐ"},
    {"phrase_id": "p194", "hanzi": "到那里", "pinyin": "dào nà lǐ"},
    {"phrase_id": "p195", "hanzi": "到北京", "pinyin": "dào běi jīng"},
    {"phrase_id": "p196", "hanzi": "到上海", "pinyin": "dào shàng hǎi"},
    {"phrase_id": "p197", "hanzi": "到机场", "pinyin": "dào jī chǎng"},
    {"phrase_id": "p198", "hanzi": "到车站", "pinyin": "dào chē zhàn"},
    {"phrase_id": "p199", "hanzi": "到酒店", "pinyin": "dào jiǔ diàn"},
    {"phrase_id": "p200", "hanzi": "到学校", "pinyin": "dào xué xiào"},
    {"phrase_id": "p201", "hanzi": "我想问", "pinyin": "wǒ xiǎng wèn"},
    {"phrase_id": "p202", "hanzi": "你叫什么", "pinyin": "nǐ jiào shén me"},
    {"phrase_id": "p203", "hanzi": "我叫小明", "pinyin": "wǒ jiào xiǎo míng"},
    {"phrase_id": "p204", "hanzi": "你几岁", "pinyin": "nǐ jǐ suì"},
    {"phrase_id": "p205", "hanzi": "我二十岁", "pinyin": "wǒ èr shí suì"},
    {"phrase_id": "p206", "hanzi": "你多大", "pinyin": "nǐ duō dà"},
    {"phrase_id": "p207", "hanzi": "我多大", "pinyin": "wǒ duō dà"},
    {"phrase_id": "p208", "hanzi": "你是哪里人", "pinyin": "nǐ shì nǎ lǐ rén"},
    {"phrase_id": "p209", "hanzi": "我是美国人", "pinyin": "wǒ shì měi guó rén"},
    {"phrase_id": "p210", "hanzi": "我是学生", "pinyin": "wǒ shì xué shēng"},
    {"phrase_id": "p211", "hanzi": "我是老师", "pinyin": "wǒ shì lǎo shī"},
    {"phrase_id": "p212", "hanzi": "我在上课", "pinyin": "wǒ zài shàng kè"},
    {"phrase_id": "p213", "hanzi": "我在开会", "pinyin": "wǒ zài kāi huì"},
    {"phrase_id": "p214", "hanzi": "我在吃饭", "pinyin": "wǒ zài chī fàn"},
    {"phrase_id": "p215", "hanzi": "我在睡觉", "pinyin": "wǒ zài shuì jiào"},
    {"phrase_id": "p216", "hanzi": "我在等你", "pinyin": "wǒ zài děng nǐ"},
    {"phrase_id": "p217", "hanzi": "我在找你", "pinyin": "wǒ zài zhǎo nǐ"},
    {"phrase_id": "p218", "hanzi": "你在干嘛", "pinyin": "nǐ zài gàn ma"},
    {"phrase_id": "p219", "hanzi": "我在干嘛", "pinyin": "wǒ zài gàn ma"},
    {"phrase_id": "p220", "hanzi": "你在做什么", "pinyin": "nǐ zài zuò shén me"},
    {"phrase_id": "p221", "hanzi": "我在做饭", "pinyin": "wǒ zài zuò fàn"},
    {"phrase_id": "p222", "hanzi": "我在洗澡", "pinyin": "wǒ zài xǐ zǎo"},
    {"phrase_id": "p223", "hanzi": "我在跑步", "pinyin": "wǒ zài pǎo bù"},
    {"phrase_id": "p224", "hanzi": "我在学习", "pinyin": "wǒ zài xué xí"},
    {"phrase_id": "p225", "hanzi": "我在复习", "pinyin": "wǒ zài fù xí"},
    {"phrase_id": "p226", "hanzi": "你吃了吗", "pinyin": "nǐ chī le ma"},
    {"phrase_id": "p227", "hanzi": "我吃了", "pinyin": "wǒ chī le"},
    {"phrase_id": "p228", "hanzi": "还没吃", "pinyin": "hái méi chī"},
    {"phrase_id": "p229", "hanzi": "一起吃饭", "pinyin": "yì qǐ chī fàn"},
    {"phrase_id": "p230", "hanzi": "一起喝咖啡", "pinyin": "yì qǐ hē kā fēi"},
    {"phrase_id": "p231", "hanzi": "一起去吧", "pinyin": "yì qǐ qù ba"},
    {"phrase_id": "p232", "hanzi": "我们走吧", "pinyin": "wǒ men zǒu ba"},
    {"phrase_id": "p233", "hanzi": "我们回家", "pinyin": "wǒ men huí jiā"},
    {"phrase_id": "p234", "hanzi": "我们开始", "pinyin": "wǒ men kāi shǐ"},
    {"phrase_id": "p235", "hanzi": "我们继续", "pinyin": "wǒ men jì xù"},
    {"phrase_id": "p236", "hanzi": "我们结束", "pinyin": "wǒ men jié shù"},
    {"phrase_id": "p237", "hanzi": "休息一下", "pinyin": "xiū xi yí xià"},
    {"phrase_id": "p238", "hanzi": "喝点水", "pinyin": "hē diǎn shuǐ"},
    {"phrase_id": "p239", "hanzi": "吃点东西", "pinyin": "chī diǎn dōng xi"},
    {"phrase_id": "p240", "hanzi": "去洗手间", "pinyin": "qù xǐ shǒu jiān"},
    {"phrase_id": "p241", "hanzi": "洗手间在哪", "pinyin": "xǐ shǒu jiān zài nǎ"},
    {"phrase_id": "p242", "hanzi": "我迷路了", "pinyin": "wǒ mí lù le"},
    {"phrase_id": "p243", "hanzi": "我找不到", "pinyin": "wǒ zhǎo bú dào"},
    {"phrase_id": "p244", "hanzi": "你能帮我吗", "pinyin": "nǐ néng bāng wǒ ma"},
    {"phrase_id": "p245", "hanzi": "你能说中文吗", "pinyin": "nǐ néng shuō zhōng wén ma"},
    {"phrase_id": "p246", "hanzi": "我说中文", "pinyin": "wǒ shuō zhōng wén"},
    {"phrase_id": "p247", "hanzi": "我学中文", "pinyin": "wǒ xué zhōng wén"},
    {"phrase_id": "p248", "hanzi": "说得很好", "pinyin": "shuō de hěn hǎo"},
    {"phrase_id": "p249", "hanzi": "说得不错", "pinyin": "shuō de bú cuò"},
    {"phrase_id": "p250", "hanzi": "再试一次", "pinyin": "zài shì yí cì"},
    {"phrase_id": "p251", "hanzi": "没听见", "pinyin": "méi tīng jiàn"},
    {"phrase_id": "p252", "hanzi": "听到了", "pinyin": "tīng dào le"},
    {"phrase_id": "p253", "hanzi": "看到了", "pinyin": "kàn dào le"},
    {"phrase_id": "p254", "hanzi": "我明天去", "pinyin": "wǒ míng tiān qù"},
    {"phrase_id": "p255", "hanzi": "我今天去", "pinyin": "wǒ jīn tiān qù"},
    {"phrase_id": "p256", "hanzi": "我现在去", "pinyin": "wǒ xiàn zài qù"},
    {"phrase_id": "p257", "hanzi": "我等一下", "pinyin": "wǒ děng yí xià"},
    {"phrase_id": "p258", "hanzi": "我马上来", "pinyin": "wǒ mǎ shàng lái"},
    {"phrase_id": "p259", "hanzi": "你放心", "pinyin": "nǐ fàng xīn"},
    {"phrase_id": "p260", "hanzi": "我放心", "pinyin": "wǒ fàng xīn"},
    {"phrase_id": "p261", "hanzi": "我知道了", "pinyin": "wǒ zhī dào le"},
    {"phrase_id": "p262", "hanzi": "我忘了", "pinyin": "wǒ wàng le"},
    {"phrase_id": "p263", "hanzi": "我记得", "pinyin": "wǒ jì de"},
    {"phrase_id": "p264", "hanzi": "我不记得", "pinyin": "wǒ bù jì de"},
    {"phrase_id": "p265", "hanzi": "别说了", "pinyin": "bié shuō le"},
    {"phrase_id": "p266", "hanzi": "别闹了", "pinyin": "bié nào le"},
    {"phrase_id": "p267", "hanzi": "开玩笑", "pinyin": "kāi wán xiào"},
    {"phrase_id": "p268", "hanzi": "别开玩笑", "pinyin": "bié kāi wán xiào"},
    {"phrase_id": "p269", "hanzi": "你说得对", "pinyin": "nǐ shuō de duì"},
    {"phrase_id": "p270", "hanzi": "你说得好", "pinyin": "nǐ shuō de hǎo"},
    {"phrase_id": "p271", "hanzi": "我同意", "pinyin": "wǒ tóng yì"},
    {"phrase_id": "p272", "hanzi": "我不同意", "pinyin": "wǒ bù tóng yì"},
    {"phrase_id": "p273", "hanzi": "没意思", "pinyin": "méi yì si"},
    {"phrase_id": "p274", "hanzi": "有意思", "pinyin": "yǒu yì si"},
    {"phrase_id": "p275", "hanzi": "真有趣", "pinyin": "zhēn yǒu qù"},
    {"phrase_id": "p276", "hanzi": "太有趣了", "pinyin": "tài yǒu qù le"},
    {"phrase_id": "p277", "hanzi": "太安静了", "pinyin": "tài ān jìng le"},
    {"phrase_id": "p278", "hanzi": "太吵了", "pinyin": "tài chǎo le"},
    {"phrase_id": "p279", "hanzi": "太冷了", "pinyin": "tài lěng le"},
    {"phrase_id": "p280", "hanzi": "太热了", "pinyin": "tài rè le"},
    {"phrase_id": "p281", "hanzi": "下雨了", "pinyin": "xià yǔ le"},
    {"phrase_id": "p282", "hanzi": "下雪了", "pinyin": "xià xuě le"},
    {"phrase_id": "p283", "hanzi": "刮风了", "pinyin": "guā fēng le"},
    {"phrase_id": "p284", "hanzi": "天气真好", "pinyin": "tiān qì zhēn hǎo"},
    {"phrase_id": "p285", "hanzi": "天气不好", "pinyin": "tiān qì bù hǎo"},
    {"phrase_id": "p286", "hanzi": "我喜欢你", "pinyin": "wǒ xǐ huān nǐ"},
    {"phrase_id": "p287", "hanzi": "我想试试", "pinyin": "wǒ xiǎng shì shì"},
    {"phrase_id": "p288", "hanzi": "我想看看", "pinyin": "wǒ xiǎng kàn kan"},
    {"phrase_id": "p289", "hanzi": "我想听听", "pinyin": "wǒ xiǎng tīng ting"},
    {"phrase_id": "p290", "hanzi": "我想学学", "pinyin": "wǒ xiǎng xué xue"},
    {"phrase_id": "p291", "hanzi": "我先走了", "pinyin": "wǒ xiān zǒu le"},
    {"phrase_id": "p292", "hanzi": "我先回去", "pinyin": "wǒ xiān huí qù"},
    {"phrase_id": "p293", "hanzi": "你先走吧", "pinyin": "nǐ xiān zǒu ba"},
    {"phrase_id": "p294", "hanzi": "你先说吧", "pinyin": "nǐ xiān shuō ba"},
    {"phrase_id": "p295", "hanzi": "我先看看", "pinyin": "wǒ xiān kàn kan"},
    {"phrase_id": "p296", "hanzi": "我再想想", "pinyin": "wǒ zài xiǎng xiǎng"},
    {"phrase_id": "p297", "hanzi": "我再试试", "pinyin": "wǒ zài shì shì"},
    {"phrase_id": "p298", "hanzi": "我再问问", "pinyin": "wǒ zài wèn wen"},
    {"phrase_id": "p299", "hanzi": "回头再说", "pinyin": "huí tóu zài shuō"},
    {"phrase_id": "p300", "hanzi": "以后再说", "pinyin": "yǐ hòu zài shuō"},
]
TONE_MARKS = { # very small tone-mark lookup for common vowel diacritics
    "ā":1,"á":2,"ǎ":3,"à":4,
    "ē":1,"é":2,"ě":3,"è":4,
    "ī":1,"í":2,"ǐ":3,"ì":4,
    "ō":1,"ó":2,"ǒ":3,"ò":4,
    "ū":1,"ú":2,"ǔ":3,"ù":4,
    "ǖ":1,"ǘ":2,"ǚ":3,"ǜ":4,
} # if none found -> neutral/unknown

# copy `PHRASES` list into DB once
def seed_phrases_if_empty():
    Session = get_session(current_app) # get scoped session
    db = Session() # open session

    count = db.query(Phrase).count() # how many phrases exist
    if count == 0: # only seed if DB is empty
        for ph in PHRASES:
            db.add(Phrase(phrase_id = ph["phrase_id"], hanzi = ph["hanzi"], pinyin = ph["pinyin"])) # insert phrase
        db.commit() # persist to SQLite

# detect tone number from tone mark (super simple)
def tone_from_pinyin_syllable(syl):
    for ch in syl:
        if ch in TONE_MARKS:
            return TONE_MARKS[ch]
    return 5 # treat as neutral/unknown

# fetch phrase dict by phrase_id
def get_phrase_by_id(phrase_id):
    for ph in PHRASES:
        if ph["phrase_id"] == phrase_id:
            return ph
    return None

# split pinyin string into syllables
def pinyin_syllables(pinyin):
    return [s for s in pinyin.strip().split() if s]

# map "/uploads/xyz.webm" -> UPLOAD_DIR/"xyz.webm"
def file_url_to_path(file_url):
    path = urlparse(file_url).path # strip domain/query
    fname = Path(path).name # just the filename
    return UPLOAD_DIR / fname

# convert anything -> wav 16k mono
def ffmpeg_to_wav16k_mono(src_path, dst_path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_path), "-ac", "1", "-ar", "16000", str(dst_path)],
        check = True,
        stdout = subprocess.DEVNULL,
        stderr = subprocess.DEVNULL
    )

# return time array + f0 array
def extract_f0(wav_path):
    snd = parselmouth.Sound(str(wav_path)) # load audio
    pitch = snd.to_pitch(time_step = 0.01, pitch_floor = 75, pitch_ceiling = 500) # basic pitch tracking
    t = pitch.xs() # time stamps
    f0 = pitch.selected_array["frequency"] # Hz; 0 where unvoiced
    f0 = np.where(f0 > 0, f0, np.nan) # replace 0 with NaN (for unvoiced)
    return t, f0, snd.duration

# return (score, label) for one syllable window
def score_window(f0_win, tone):
    x = f0_win[np.isfinite(f0_win)] # drop NaNs (e.g. unvoiced)
    if len(x) < 5: # if not enough voiced frames:
        return 20, "too unvoiced/no pitch"

    start = x[0]
    end = x[-1]
    minimum = np.min(x)

    # normalze using log base 2 so "relative change" is nicer than raw hertz
    slope = np.log2(end) - np.log2(start) # positive = rising, negative = falling
    rng = np.log2(np.max(x)) - np.log2(np.min(x)) # movement amount

    # tone "grading"
    if tone == 1:
        if abs(slope) < 0.05 and rng < 0.10:
            return 95, "ok (level)"
        return 60, "too much movement (tone 1 should be level)"
    if tone == 2:
        if slope > 0.08:
            return 95, "ok (rising)"
        return 55, "not rising enough (tone 2)"
    if tone == 4:
        if slope < -0.08:
            return 95, "ok (falling)"
        return 55, "not falling enough (tone 4)"
    if tone == 3:
        # check for dip (min noticeably below both ends)
        if (minimum < min(start, end) * 0.92) and rng > 0.10:
            return 90, "ok (dip)"
        return 55, "missing dip (tone 3-ish)"
    # tone 5 or unknown
    return 75, "neutral/unknown tone"

# main analysis: per-syllable scores + plot
def analyze_and_plot(wav_path, phrase):
    t, f0, dur = extract_f0(wav_path) # compute pitch track
    syls = pinyin_syllables(phrase["pinyin"]) # list syllables
    tones = [tone_from_pinyin_syllable(s) for s in syls] # tone numbers per syllable

    n = max(1, len(syls)) # number of windows
    edges = np.linspace(0, dur, n + 1) # uniform segmentation

    syllable_results = []
    bad_spans = []

    for i in range(n):
        a, b = edges[i], edges[i + 1] # window bounds
        mask = (t >= a) & (t < b) # f0 samples inside window
        score, label = score_window(f0[mask], tones[i]) # compute score + label

        syllable_results.append({
            "idx": i,
            "syllable": syls[i],
            "tone": tones[i],
            "score": int(score),
            "label": label,
            "t0": float(a),
            "t1": float(b),
        })

        if score < 70: # threshold for "bad" syllable highlight
            bad_spans.append((a, b))

    overall = int(round(np.mean([s["score"] for s in syllable_results]))) # overall score

    # plot f0 + highlight bad spans
    fig = plt.figure(figsize = (8, 3)) # wide, short
    ax = fig.add_subplot(111)
    ax.plot(t, f0, linewidth = 1) # pitch track

    for (a, b) in bad_spans:
        ax.axvspan(a, b, alpha = 0.25) # highlight mistakes

    ax.set_xlabel("time (s)")
    ax.set_ylabel("f0 (Hz)")
    ax.set_title(f'{phrase["hanzi"]}   ({phrase["pinyin"]})   score={overall}')

    fig.tight_layout()

    return overall, syllable_results, fig

# serve uploaded audio files back to browser
@apiapp.get("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# serve uploaded artifacts back to browser
@apiapp.get("/artifacts/<run_id>/<path:filename>")
def artifact(run_id, filename):
    return send_from_directory(ARTIFACT_DIR / run_id, filename) # serve plot.png, etc.

# get a random phrase from the phrase bank DB
@apiapp.get("/phrase")
def phrase():
    seed_phrases_if_empty() # ensure DB has phrases

    Session = get_session(current_app) # scoped session factory
    db = Session() # session

    # quick random phrase:
    ph = db.query(Phrase).order_by(func.random()).first() # pick random row
    return jsonify({"phrase_id": ph.phrase_id, "hanzi": ph.hanzi, "pinyin": ph.pinyin})

# compare recording to DB
@apiapp.post("/compare")
def compare():
    data = request.get_json(force = True) # read JSON body
    phrase_id = data.get("phrase_id", "") # grab phrase_id
    file_url = data.get("file_url", "") # grab last uploaded file_url

    phrase = get_phrase_by_id(phrase_id) # lookup phrase info
    if not phrase:
        return jsonify({"error": "unknown phrase_id"}), 400

    src_path = file_url_to_path(file_url) # map url -> disk file path
    if not src_path.exists():
        return jsonify({"error": "audio file not found on server"}), 404

    run_id = f"{int(time.time())}_{uuid4().hex[:8]}" # unique id for artifacts
    out_dir = ARTIFACT_DIR / run_id # per-compare artifacts folder
    out_dir.mkdir(exist_ok = True) # ensure folder exists

    wav_path = out_dir / "user.wav" # normalized audio location
    plot_path = out_dir / "plot.png" # plot image location

    ffmpeg_to_wav16k_mono(src_path, wav_path) # convert audio to wav 16k mono
    overall, syllables, fig = analyze_and_plot(wav_path, phrase) # analyze + build plot
    fig.savefig(plot_path, dpi = 160) # save the plot
    plt.close(fig) # avoid matplotlib memory buildup

    Session = get_session(current_app) # scoped session factory
    db = Session() # session

    db.add(Attempt( # save attempt result
        phrase_id = phrase_id,
        file_url = file_url,
        score = overall,
        syllables_json = json.dumps(syllables, ensure_ascii = False),
        plot_url = url_for("apiroutes.artifact", run_id = run_id, filename = "plot.png"),
    ))
    db.commit() # write to sqlite

    return jsonify({
        "score": overall,
        "syllables": syllables,
        "plot_url": url_for("apiroutes.artifact", run_id = run_id, filename = "plot.png"),
    })

# serve generated TTS files back to browser
@apiapp.get("/tts/<path:filename>")
def tts_file(filename):
    return send_from_directory(TTS_DIR, filename) # browser can play this URL

# generate TTS audio from current phrase w/ OpenAI call
@apiapp.post("/tts")
def tts():
    Session = get_session(current_app) # scoped session factory
    db = Session() # open session

    j = request.get_json(silent = True) or {} # parse JSON body
    phrase_id = j.get("phrase_id", "") # phrase_id from frontend

    if not phrase_id: # require phrase_id
        return jsonify({"error": "missing phrase_id"}), 400

    ph = db.get(Phrase, phrase_id) # fetch Phrase row by primary key from DB
    if not ph: # handle unknown phrase_id
        return jsonify({"error": "unknown phrase_id"}), 404

    text = ph.hanzi # speak the hanzi text

    out_name = f"{uuid4().hex}__tts.mp3" # unique filename
    out_path = TTS_DIR / out_name # full disk path

    # OpenAI TTS: model + voice + input text (mp3 is default)
    with client.audio.speech.with_streaming_response.create(
        model = "gpt-4o-mini-tts", # TTS model
        voice = "marin", # built-in voice
        input = text, # what gets spoken
        instructions = "Speak Mandarin Chinese (zh-CN) clearly and naturally for a learner.", # style control
        response_format = "mp3",
        speed = 0.95, # slightly slower for learners
    ) as response:
        response.stream_to_file(out_path) # write audio bytes to disk

    return jsonify({ # return playable URL to frontend
        "tts_url": url_for("apiroutes.tts_file", filename = out_name), # adjust blueprint endpoint if needed
        "phrase_id": phrase_id
    })

# upload endpoint
@apiapp.post("/upload")
def upload():
    if "audio" not in request.files:
        return jsonify({"error": "missing form field: audio"}), 400
    
    f = request.files["audio"]
    if not f.filename: # ensure browser doesn't come with empty filename
        return jsonify({"error": "empty filename"}), 400
    
    ext = Path(f.filename).suffix.lower() or ".webm" # extract file extension; default to `.webm`

    base = secure_filename(Path(f.filename).stem)[:40] or "rec" # create base name for disk readability; `secure_filename` strips weird chars

    out_name = f"{uuid4().hex}__{base}{ext}" # create unique filenames

    phrase_id = request.form.get("phrase_id", "") # initialize `phrase_id` var
    (UPLOAD_DIR / f"{out_name}.json").write_text( # write phrase_id metadata next to audio file
        json.dumps({"phrase_id": phrase_id}, ensure_ascii = False, indent = 2)
    )

    out_path = UPLOAD_DIR / out_name
    f.save(out_path) # save file to disk

    return jsonify( # return a URL
        {
            "file_url": url_for("apiroutes.uploads", filename = out_name),
            "bytes_saved": out_path.stat().st_size
        }
    )