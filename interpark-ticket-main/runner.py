"""NOL World / onestop 半自动抢票主流程。

分工：
  你手动：在脚本开的 Chrome 里登录 → 点预订 → 走到验证码弹出 → 回脚本按回车
  脚本自动：验证码(文字版OCR/滑块喊人) → 选座(最贵优先) → 选数量 → 填手机+勾同意 → 响铃停手
  你手动：亲自刷卡付款

登录、点预订、付款都由人工完成，脚本不碰——最稳、最安全。
"""

import base64
import logging
import os
import time

import requests

import onestop


# ---- 百度 OCR：用 API Key/Secret 自动换 token，识别 base64 图片 ----
_baidu_token = None


def _get_baidu_token(api_key, secret_key):
    global _baidu_token
    if _baidu_token:
        return _baidu_token
    resp = requests.post(
        "https://aip.baidubce.com/oauth/2.0/token",
        params={
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": secret_key,
        },
    )
    _baidu_token = resp.json().get("access_token")
    if not _baidu_token:
        logging.error("获取百度 token 失败：%s", resp.text)
    return _baidu_token


def make_ocr(api_key, secret_key):
    """返回一个 ocr(base64_str)->识别文本 的函数，供 solve_text_captcha 用。"""
    import re

    def ocr(b64):
        token = _get_baidu_token(api_key, secret_key)
        if not token:
            return ""
        url = (
            "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
            "?access_token=" + token
        )
        resp = requests.post(
            url,
            data={"image": b64},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        words = resp.json().get("words_result", [])
        text = "".join(w.get("words", "") for w in words)
        # 验证码通常是字母数字，去掉空格和杂符
        return re.sub(r"[^A-Za-z0-9]", "", text)

    return ocr


# ---- 跨平台响铃 ----
def alarm():
    import sys

    try:
        if sys.platform.startswith("win"):
            import winsound

            for _ in range(5):
                winsound.Beep(1000, 400)
        elif sys.platform == "darwin":
            os.system("afplay /System/Library/Sounds/Ping.aiff -t 10")
        else:
            for _ in range(10):
                print("\a", end="", flush=True)
                time.sleep(1)
    except Exception:
        logging.error("响铃失败")


# ---- 开浏览器：用固定配置目录，这样你在脚本窗口里登录后状态能留住 ----
def _build_options(use_profile):
    from selenium import webdriver

    options = webdriver.ChromeOptions()
    if use_profile:
        # 固定 profile 目录：登录状态、cookie 存这，脚本操作的就是你登录的窗口
        profile_dir = os.path.join(_app_dir(), "chrome-profile")
        options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument("--disable-blink-features=AutomationControlled")
    return options


def make_driver(say=None):
    """开 Chrome。先试固定 profile；被占用就退回无 profile，并把原因说清。"""
    from selenium import webdriver

    def _log(m):
        logging.info(m)
        if say:
            say(m)

    try:
        return webdriver.Chrome(options=_build_options(use_profile=True))
    except Exception as e:
        _log(f"用固定配置开 Chrome 失败：{e}")
        _log("多半是 Chrome 已经开着（配置目录被占用）。")
        _log("正在改用临时配置重试（这样就得每次手动登录）……")
        try:
            return webdriver.Chrome(options=_build_options(use_profile=False))
        except Exception as e2:
            _log(f"再次失败：{e2}")
            _log("请确认：1) 已装 Google Chrome  2) 先关掉所有 Chrome 窗口再试。")
            raise


def _app_dir():
    import sys

    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def run(cfg, wait_takeover=None, status=None):
    """半自动主流程。

    cfg: dict，含 SeatTotal / PhoneNo / BaiduApiKey / BaiduSecretKey
    wait_takeover: 无参函数，脚本开好浏览器后调用它阻塞，等你在窗口里登录、
                   点预订、走到验证码弹出后，再放行（GUI 里点「接手」按钮）。
    status: 单参函数，用来把进度回报给 GUI 日志框。
    """
    def say(msg):
        logging.info(msg)
        if status:
            status(msg)

    want = int(cfg.get("SeatTotal") or 1)
    phone = cfg.get("PhoneNo") or ""
    ocr = make_ocr(cfg.get("BaiduApiKey", ""), cfg.get("BaiduSecretKey", ""))

    say("正在打开 Chrome……请在弹出的窗口里手动登录 NOL World，")
    say("点预订、走到「验证码弹出」这一步，然后回来点「接手」。")
    driver = make_driver(say=say)
    driver.get("https://world.nol.com/zh-CN/ticket")

    # 阻塞，等你手动操作到验证码页再点「接手」
    if wait_takeover:
        wait_takeover()
    say("已接手，开始自动处理……")

    # 1) 验证码
    kind = onestop.detect_captcha(driver)
    if kind == onestop.CAPTCHA_TEXT:
        say("检测到图片验证码，OCR 识别中……")
        if not onestop.solve_text_captcha(driver, ocr):
            say("验证码没自动过，请手动输入后再点一次「接手」。")
            if wait_takeover:
                wait_takeover()
    elif kind == onestop.CAPTCHA_SLIDER:
        say("是滑块验证码，脚本过不了，请手动拖动完成后再点「接手」。")
        alarm()
        if wait_takeover:
            wait_takeover()
    else:
        say("没检测到验证码，继续。")

    # 2) 选座（最贵优先）
    say("正在挑选座位（最贵优先）……")
    picked = onestop.choose_seat_auto(driver, want_count=want, log=say)
    if not picked:
        say("没找到可选座位：可能座位图没加载完、结构变了、或已售罄。")
        say("如果你能看到座位图，请把当时的页面截图/HTML 发给作者。")
        alarm()
        return
    say(f"已选 {len(picked)} 个座位：{picked}")

    # 3) 选数量并订购
    say("确认数量并点訂購……")
    onestop.set_quantity_and_order(driver, want_count=want)

    # 4) 填手机 + 勾同意
    say("填手机号、勾选同意条款……")
    onestop.fill_info_and_agree(driver, phone=phone)

    # 5) 到付款前停手，响铃喊你刷卡
    say("★ 已就绪！请在浏览器里核对信息并亲手完成付款。★")
    alarm()
