"""配置读写：把界面填的信息存到 settings.json，供抢票逻辑读取。

打包成 exe 后，settings.json 会放在 exe 同目录（而不是临时解压目录），
这样用户填过的信息下次打开还在。
"""

import json
import os
import sys


# 所有字段及默认值。界面按这个顺序生成输入框。
# key: (中文标签, 默认值, 是否敏感/密码框)
# A 方案（半自动）：人工登录、人工刷卡。
# 姓名/生日/邮箱新站从账号自动带（只读），无须填。
# 所以只留：抢几张、手机号。百度 OCR 备用（新站是否还有验证码待确认）。
FIELDS = [
    ("SeatTotal",      "抢几张票",                "1",          False),
    ("PhoneNo",        "手机号码（只填数字）",     "",           False),
    ("BaiduApiKey",    "百度 OCR API Key（备用）", "",           False),
    ("BaiduSecretKey", "百度 OCR Secret Key（备用）", "",        True),
]

# 数值型字段（读回来要转 int）
INT_FIELDS = {"SeatTotal"}


def app_dir():
    """返回配置文件应存放的目录。

    - 打包成 exe（sys.frozen）时用 exe 所在目录；
    - 普通脚本运行时用本文件所在目录。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def settings_path():
    return os.path.join(app_dir(), "settings.json")


def defaults():
    return {key: default for key, _label, default, _secret in FIELDS}


def load():
    """读取 settings.json，缺失的键用默认值补齐。"""
    data = defaults()
    path = settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for key in data:
                if key in saved:
                    data[key] = saved[key]
        except (json.JSONDecodeError, OSError):
            # 文件损坏就当作空配置，用默认值
            pass
    return data


def save(data):
    """把界面收集到的配置写回 settings.json。"""
    path = settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path
