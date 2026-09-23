"""NOL World / Interpark onestop 新版选座逻辑。

老站（globalinterpark）靠 iframe + TmgsTable + <area> + 手工 list_order。
2025-12 改版后 onestop 是 React 页面，座位是 SVG <circle>：

    <circle id="seat_block_商品:场次:区块:座号"
            class="SeatMap_seatSvg__XXXX js-seat"        <- 可选
            fill="#17b3ff" stroke="#17b3ff">

    <circle ... class="SeatMap_seatSvg__XXXX SeatMap_disabled__YYYY js-seat"
            fill="#edeff3">                              <- 售罄/不可选

判定「可选」用双保险：class 不含 disabled，且颜色不是灰的（#edeff3）。
这两条哪怕改版后哈希 class 变了，颜色兜底仍多半有效。

价格档由页面图例（SeatGradeLayer）给出：每档一个颜色圆点 + 档名 + 价格。
「优先最贵」= 读图例按价格排序，从最贵档的颜色开始找可选座位。
颜色不能写死——每场对应关系都不同。
"""

import re


SOLD_FILL = "#edeff3"  # 售罄座位的灰色


def parse_price_from_text(text):
    """从 '609,000元' / '154,000 원' 这类文本抽出数字，失败返回 0。"""
    if not text:
        return 0
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else 0


def rgb_to_hex(rgb_str):
    """'124, 104, 238' -> '#7c68ee'。"""
    parts = [int(x) for x in rgb_str.split(",")]
    return "#%02x%02x%02x" % tuple(parts[:3])


def parse_grades(html):
    """解析图例，返回按价格从高到低排序的 [(hex颜色, 档名, 价格), ...]。"""
    items = re.findall(
        r"background-color:\s*rgb\(([^)]+)\).*?gradeName[^>]*>([^<]*)<"
        r".*?gradePrice[^>]*>([^<]*)<",
        html,
        re.S,
    )
    grades = []
    for rgb, name, price in items:
        grades.append(
            (rgb_to_hex(rgb), name.strip(), parse_price_from_text(price))
        )
    grades.sort(key=lambda g: g[2], reverse=True)
    return grades


def preferred_colors(html):
    """按「最贵优先」返回颜色列表（十六进制小写）。"""
    return [g[0].lower() for g in parse_grades(html) if g[2] > 0]


# ---- 下面是 Selenium 运行时用的部分（离线解析测试用不到） ----

# 找可选座位：js-seat 且 class 不含 disabled 且 fill 不是灰色。
# 用 CSS 先粗筛 .js-seat:not([class*="disabled"])，再按颜色精筛。
_SELECTABLE_CSS = 'circle.js-seat:not([class*="disabled"])'


def find_selectable_seats(driver, color=None):
    """返回可选座位元素列表。给了 color 就只返回该颜色（某价格档）的。"""
    from selenium.webdriver.common.by import By

    seats = driver.find_elements(By.CSS_SELECTOR, _SELECTABLE_CSS)
    result = []
    for s in seats:
        fill = (s.get_attribute("fill") or "").lower()
        if fill == SOLD_FILL:  # 双保险：颜色兜底排除售罄
            continue
        if color and fill != color:
            continue
        result.append(s)
    return result


def wait_and_focus_seatmap(driver, timeout=20, log=None):
    """等座位图加载出来。返回找到的座位数。

    新版 onestop 座位直接在主文档,不在 iframe。
    """
    import time
    from selenium.webdriver.common.by import By

    def _log(m):
        if log:
            log(m)

    driver.switch_to.default_content()  # 确保在主文档
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = len(driver.find_elements(By.CSS_SELECTOR, "circle.js-seat"))
        if n > 0:
            _log(f"主文档找到 {n} 个座位")
            return n
        time.sleep(0.5)
    _log("等了 %d 秒仍没找到 circle.js-seat" % timeout)
    return 0


# ---- 选座:旧站(interpark) vs 新站(nol) 双模式 ----

def choose_seat_auto(driver, want_count=1, log=None):
    """自动判断旧站/新站,选择对应的选座逻辑。

    旧站(interpark/globalinterpark):iframe + area 区域选座
    新站(nol):SVG circle.js-seat 直接选座
    """
    import logging
    if log is None:
        log = lambda m: None

    url = driver.current_url.lower()
    if "nol.com" in url:
        log("检测到新站(NOL),使用 SVG 选座逻辑")
        return choose_best_seat(driver, want_count, log)
    elif "interpark.com" in url:
        log("检测到旧站(Interpark),使用区域选座逻辑")
        return choose_seat_old(driver, want_count, log)
    else:
        log(f"未识别的域名:{url},尝试新站逻辑")
        return choose_best_seat(driver, want_count, log)


def choose_seat_old(driver, want_count=1, log=None):
    """旧站(interpark)选座逻辑:遍历所有区域,找到有票的就点。

    策略:点每个area区域 → 检查座位 → 按颜色选最贵的。
    """
    import time
    import logging
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.wait import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    if log is None:
        log = lambda m: None

    # 等待并切到 ifrmSeat
    try:
        driver.switch_to.default_content()
        WebDriverWait(driver, 20, 0.5).until(EC.presence_of_element_located((By.ID, 'ifrmSeat')))
        driver.switch_to.frame("ifrmSeat")
        log("已切入 ifrmSeat")
    except Exception as e:
        log(f"未找到 ifrmSeat iframe:{e}")
        return 0

    # 循环等待区域地图或座位出现(最多等30秒)
    log("等待区域地图或座位加载...")
    deadline = time.time() + 30
    areas = []
    seats = []

    while time.time() < deadline:
        areas = driver.find_elements(By.TAG_NAME, "area")
        seats = driver.find_elements(By.CSS_SELECTOR, "span.SeatN")

        if len(areas) > 0 or len(seats) > 0:
            log(f"加载完成:area={len(areas)}, seats={len(seats)}")
            break

        time.sleep(0.5)

    if len(areas) == 0 and len(seats) == 0:
        log("等待30秒后仍未找到区域或座位")
        return 0

    # 如果直接有座位,不需要点区域
    if len(seats) > 0:
        log(f"直接找到 {len(seats)} 个座位,无需选择区域")
        picked = _pick_seats_by_color(driver, seats, want_count, log)
        if picked > 0:
            log(f"已选{picked}个座位,点下一步")
            time.sleep(0.5)
            driver.switch_to.parent_frame()
            if _click_next_button(driver, log):
                return picked
            else:
                log("未找到下一步按钮,但已选座位")
                return picked
        else:
            log("找到座位但点不上")
            return 0

    # 有区域地图,逐个尝试
    if len(areas) > 0:
        log(f"检测到 {len(areas)} 个区域,逐个尝试")
        return _choose_seat_by_trying_areas(driver, want_count, log, areas)

    return 0


def _choose_seat_by_trying_areas(driver, want_count, log, areas):
    """遍历所有区域,找到有票的就点。

    按区域编号排序(编号小的通常是好位置)。
    """
    import time
    import re
    from selenium.webdriver.common.by import By

    # 提取区域编号并排序
    area_list = []
    for area in areas:
        href = area.get_attribute("href") or ""
        title = area.get_attribute("title") or ""
        # 从 href 提取区域编号 GetBlockSeatList('', '', '020')
        match = re.search(r"'(\d{3})'", href)
        if match:
            area_no = match.group(1)
            area_list.append((int(area_no), area, title))

    # 按编号排序(小号优先,通常是前排/VIP)
    area_list.sort(key=lambda x: x[0])
    log(f"按区域编号排序,将尝试前{min(20, len(area_list))}个区域")

    # 逐个尝试(最多试20个,避免太慢)
    for area_no, area, title in area_list[:20]:
        try:
            log(f"尝试区域 {area_no:03d} ({title})...")

            # 点击区域
            try:
                area.click()
            except:
                driver.execute_script("arguments[0].click();", area)

            time.sleep(0.8)

            # 切到 ifrmSeatDetail(有些站点会切到这个iframe显示座位)
            try:
                driver.switch_to.parent_frame()
                driver.switch_to.frame("ifrmSeatDetail")
            except:
                # 没有ifrmSeatDetail,继续在ifrmSeat里找
                driver.switch_to.parent_frame()
                driver.switch_to.frame("ifrmSeat")

            # 等待座位加载
            time.sleep(0.5)

            # 找座位
            seats = driver.find_elements(By.CSS_SELECTOR, "span.SeatN")

            if len(seats) > 0:
                log(f"区域 {area_no:03d} 找到 {len(seats)} 个座位!")
                picked = _pick_seats_by_color(driver, seats, want_count, log)

                if picked > 0:
                    log(f"已选{picked}个座位,点下一步")
                    time.sleep(0.5)
                    # 点"下一步"
                    driver.switch_to.parent_frame()
                    if _click_next_button(driver, log):
                        return picked
                    else:
                        log("未找到下一步按钮,但已选座位")
                        return picked
                else:
                    log(f"区域 {area_no:03d} 座位点不上,换下一个区域")
            else:
                log(f"区域 {area_no:03d} 无座位")

            # 回到 ifrmSeat 继续下一个区域
            driver.switch_to.parent_frame()
            driver.switch_to.frame("ifrmSeat")
            time.sleep(0.3)

        except Exception as e:
            log(f"区域 {area_no:03d} 异常:{e},继续下一个")
            try:
                driver.switch_to.parent_frame()
                driver.switch_to.frame("ifrmSeat")
            except:
                pass
            continue

    log("遍历完所有区域都没找到可选座位")
    return 0


def _pick_seats_by_color(driver, seats, want_count, log):
    """从座位列表中按颜色优先级选座。"""
    import time

    # 按背景色排序
    seats_with_color = []
    for seat in seats[:200]:
        try:
            bg = seat.value_of_css_property("background-color")
            title = seat.get_attribute("title") or ""
            seats_with_color.append((seat, bg, title))
        except:
            continue

    def color_priority(item):
        _, bg, _ = item
        try:
            import re
            match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', bg)
            if match:
                r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if r > 100 and b > 100:  # 紫色VIP
                    return 0
                elif g > 100:  # 绿色R Seat
                    return 1
                else:  # 蓝色S Seat
                    return 2
        except:
            pass
        return 999

    seats_with_color.sort(key=color_priority)

    # 点选座位
    picked = 0
    for seat, bg, title in seats_with_color[:want_count * 5]:
        try:
            onclick = seat.get_attribute("onclick")
            if onclick:
                driver.execute_script(onclick)
            else:
                driver.execute_script("arguments[0].click();", seat)

            picked += 1
            log(f"已点座位(第{picked}个):{title[:40]}")
            time.sleep(0.3)

            if picked >= want_count:
                break
        except Exception as e:
            continue

    return picked


def _click_next_button(driver, log):
    """点击下一步按钮。"""
    import time
    from selenium.webdriver.common.by import By

    next_btns = [
        ("ID", "NextStepImage"),
        ("CSS_SELECTOR", "img[alt*='Next']"),
        ("CSS_SELECTOR", "a[href*='Next']"),
        ("XPATH", "//img[contains(@src,'Next') or contains(@alt,'Next')]"),
    ]

    for by_type, selector in next_btns:
        try:
            if by_type == "ID":
                btn = driver.find_element(By.ID, selector)
            elif by_type == "CSS_SELECTOR":
                btn = driver.find_element(By.CSS_SELECTOR, selector)
            elif by_type == "XPATH":
                btn = driver.find_element(By.XPATH, selector)
            btn.click()
            log("已点下一步按钮")
            time.sleep(1)
            try:
                driver.switch_to.alert.accept()
            except:
                pass
            return True
        except:
            continue

    return False


def _choose_seat_by_area(driver, want_count, log):
    """旧站区域选择模式:按优先级点区域,再选座位。"""
    import time
    from selenium.webdriver.common.by import By

    # 区域优先级(VIP优先)
    area_priority = [1, 3, 4, 33, 113, 14, 17, 27, 18, 19, 26, 28, 21, 23, 22, 25, 24, 7, 2, 15, 16, 20, 5, 6, 75, 81]
    area_names = ["VIP1", "VIP2", "VIP3", "VIP4", "VIP5", "VIP6", "VIP7", "VIP8", "VIP9", "VIP10", "VIP11", "VIP12",
                  "VIP13", "VIP14", "VIP15", "VIP16", "VIP17", "VIP18", "FLOOR1", "FLOOR2", "FLOOR3", "FLOOR4",
                  "FLOOR5", "FLOOR6", "D01", "D02"]

    # 按优先级遍历区域
    for area_idx in area_priority:
        if area_idx > len(area_names):
            continue
        area_name = area_names[area_idx - 1]
        try:
            # 找该区域的 area 元素(通过 onmouseout 属性匹配区域名)
            areas = driver.find_elements(By.TAG_NAME, "area")
            target_area = None
            for a in areas:
                onmouse = a.get_attribute("onmouseout") or ""
                if area_name in onmouse:
                    target_area = a
                    break

            if not target_area:
                continue

            log(f"尝试区域:{area_name}")
            target_area.click()
            time.sleep(0.5)

            # 切到 ifrmSeatDetail
            driver.switch_to.parent_frame()
            driver.switch_to.frame("ifrmSeatDetail")

            # 找可选座位(span 不是 SeatR/SeatT 的)
            seats = driver.find_elements(By.XPATH, "//span[not(@class='SeatR' or @class='SeatT')]")
            if len(seats) == 0:
                log(f"{area_name} 无可选座位,继续下一个区域")
                driver.switch_to.parent_frame()
                driver.switch_to.frame("ifrmSeat")
                continue

            # 点选座位(最多点 want_count 个)
            picked = 0
            for seat in seats[:want_count * 3]:  # 多试几个,防止点不上
                try:
                    seat.click()
                    picked += 1
                    log(f"已点座位(第{picked}个)")
                    time.sleep(0.2)
                    if picked >= want_count:
                        break
                except Exception:
                    continue

            if picked > 0:
                log(f"{area_name} 已选{picked}个座位,点下一步")
                # 点"下一步"
                driver.switch_to.parent_frame()
                try:
                    driver.find_element(By.ID, "NextStepImage").click()
                    time.sleep(1)
                    # 处理可能的alert
                    try:
                        driver.switch_to.alert.accept()
                    except:
                        pass
                    return picked
                except Exception as e:
                    log(f"点下一步出错:{e}")
                    return picked

            # 没选中,返回 ifrmSeat 继续
            driver.switch_to.parent_frame()
            driver.switch_to.frame("ifrmSeat")

        except Exception as e:
            log(f"区域 {area_name} 异常:{e},继续下一个")
            try:
                driver.switch_to.parent_frame()
                driver.switch_to.frame("ifrmSeat")
            except:
                pass
            continue

    log("所有优先区域都没票")
    return 0


def _choose_seat_direct(driver, want_count, log):
    """旧站直接选座模式:在 ifrmSeat 里直接找可点击座位(无区域选择)。

    适用于 globalinterpark 等直接显示座位图的页面。
    座位是 <span class="SeatN" onclick="SelectSeat(...)">。
    """
    import time
    from selenium.webdriver.common.by import By

    log("查找可选座位(直接模式)……")

    # 等待座位加载(最多10秒)
    log("等待座位图加载...")
    deadline = time.time() + 10
    seats = []
    while time.time() < deadline:
        seats = driver.find_elements(By.CSS_SELECTOR, "span.SeatN")
        if len(seats) > 0:
            break
        time.sleep(0.5)

    if len(seats) == 0:
        log("未找到可选座位(span.SeatN)")
        # 调试:看看有什么 span
        all_spans = driver.find_elements(By.TAG_NAME, "span")
        log(f"调试:iframe里总共有{len(all_spans)}个span元素")
        return 0

    log(f"找到 {len(seats)} 个可选座位")

    # 按背景色排序(越深越贵,优先VIP紫色)
    seats_with_color = []
    for seat in seats[:200]:  # 最多检查200个,避免太慢
        try:
            bg = seat.value_of_css_property("background-color")
            title = seat.get_attribute("title") or ""
            seats_with_color.append((seat, bg, title))
        except Exception:
            continue

    # 简单排序:VIP座(紫色)优先
    def color_priority(item):
        _, bg, _ = item
        try:
            import re
            match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', bg)
            if match:
                r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
                # 紫色(VIP):r和b都高
                if r > 100 and b > 100:
                    return 0
                # 绿色(R Seat):g高
                elif g > 100:
                    return 1
                # 蓝色或其他(S Seat)
                else:
                    return 2
        except Exception:
            pass
        return 999

    seats_with_color.sort(key=color_priority)

    # 点选座位(从最贵的开始)
    picked = 0
    for seat, bg, title in seats_with_color[:want_count * 5]:
        try:
            # 用 onclick 的 JS 函数点击
            onclick = seat.get_attribute("onclick")
            if onclick:
                driver.execute_script(onclick)
                log(f"已点座位(第{picked+1}个):{title[:40]}")
            else:
                driver.execute_script("arguments[0].click();", seat)
                log(f"已点座位(第{picked+1}个,用click):{title[:40]}")

            picked += 1
            time.sleep(0.3)

            if picked >= want_count:
                break
        except Exception as e:
            log(f"点击座位失败:{e}")
            continue

    if picked == 0:
        log("找到座位但都点不上")
        return 0

    log(f"已选{picked}个座位,查找下一步按钮")
    time.sleep(0.8)

    # 点"下一步"
    driver.switch_to.parent_frame()
    next_btns = [
        ("ID", "NextStepImage"),
        ("CSS_SELECTOR", "img[alt*='Next']"),
        ("CSS_SELECTOR", "a[href*='Next']"),
        ("XPATH", "//img[contains(@src,'Next') or contains(@alt,'Next')]"),
    ]

    for by_type, selector in next_btns:
        try:
            if by_type == "ID":
                btn = driver.find_element(By.ID, selector)
            elif by_type == "CSS_SELECTOR":
                btn = driver.find_element(By.CSS_SELECTOR, selector)
            elif by_type == "XPATH":
                btn = driver.find_element(By.XPATH, selector)
            btn.click()
            log("已点下一步按钮")
            time.sleep(1)
            # 处理可能的alert
            try:
                driver.switch_to.alert.accept()
            except:
                pass
            return picked
        except Exception:
            continue

    log("未找到下一步按钮,但已选座位")
    return picked


def choose_best_seat(driver, want_count=1, log=None):
    """按「最贵优先」挑并点击 want_count 个可选座位。

    返回实际点中的座位 id 列表；一个都没点到返回空列表。
    会自动等待座位图、并在 iframe 里时切进去。
    点完后会等页面底部 countCurrent 达到目标数量再返回。
    """
    import logging
    import time
    from selenium.webdriver.common.by import By

    if log is None:
        log = lambda m: None

    # 先等座位图 / 切到正确 iframe
    found = wait_and_focus_seatmap(driver, log=log)
    if found == 0:
        return []

    html = driver.page_source
    colors = preferred_colors(html)
    if not colors:
        # 图例没解析到，就不分档，按有颜色的可选座位来
        colors = [None]

    picked = []
    for color in colors:
        seats = find_selectable_seats(driver, color)
        log(f"该档有 {len(seats)} 个可选座位，尝试点击……")
        for seat in seats:
            if len(picked) >= want_count:
                break
            seat_id = seat.get_attribute("id")
            if _click_seat(driver, seat):
                picked.append(seat_id)
                log(f"已选中座位：{seat_id}")
                time.sleep(0.3)  # 给页面一点反应时间
        if len(picked) >= want_count:
            break
    if not picked:
        log("找到了可选座位但都点不中（可能需要真实鼠标事件/被遮挡）。")
        return []

    # 点完座位后,立刻点"完成選擇"(抢票要速度,不等计数器)
    log(f"已点 {len(picked)} 个座位，立刻点「完成選擇」……")
    time.sleep(0.8)  # 给页面短暂反应时间
    _click_seat_confirm(driver, log)
    return picked


def _click_seat_confirm(driver, log):
    """选座确认后,点"完成選擇"按钮进入选数量/价格页。

    React页面元素引用会stale,每次点击前重新查找。
    跳转判定:不看座位图(选数量页也有座位图),看"完成選擇"按钮消失 或 加号按钮出现。
    """
    import time
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains

    log("查找「完成選擇」按钮……")
    deadline = time.time() + 8

    while time.time() < deadline:
        try:
            # 每次循环重新查找,避免stale
            btns = driver.find_elements(By.CSS_SELECTOR, "button.EntButton_primary__UOX1_, button.entButtonGlobal")
            for btn in btns:
                txt = (btn.text or "").strip()
                is_disabled = btn.get_attribute("disabled")

                if ("完成" in txt or "選擇" in txt or "选择" in txt.lower()) and not is_disabled:
                    log(f"找到可点按钮:「{txt}」,尝试点击……")
                    # 先滚动到可见
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.2)
                    # 用ActionChains真实点击(对React更稳)
                    ActionChains(driver).move_to_element(btn).pause(0.1).click().perform()
                    time.sleep(1)

                    # 验证是否跳页:看"完成選擇"按钮是否消失 或 加号按钮出现
                    confirm_btns = driver.find_elements(By.CSS_SELECTOR, "button")
                    confirm_gone = not any("完成" in (b.text or "") and "選擇" in (b.text or "") for b in confirm_btns)
                    inc_btns = driver.find_elements(By.CSS_SELECTOR, "button[class*='incrementButton']")

                    if confirm_gone or len(inc_btns) > 0:
                        log("已跳转到选数量页")
                        return True
                    log("点击后未检测到跳转,重试……")
        except Exception as e:
            log(f"点击异常(可能stale):{e},重新查找……")

        time.sleep(0.5)

    log("等了8秒,未能成功跳转")
    return False


def _click_seat(driver, seat):
    """点一个 SVG 座位并验证是否真的被选中。

    SVG <circle> 对普通 click 常无反应，React 要真实鼠标事件序列。
    依次尝试：ActionChains 真实点击 → 派发 pointer/mouse 事件。
    选中判定：class 出现 selected/active，或 fill 变化。
    """
    import logging
    from selenium.webdriver.common.action_chains import ActionChains

    before_class = seat.get_attribute("class") or ""
    before_fill = (seat.get_attribute("fill") or "").lower()

    def _selected():
        c = (seat.get_attribute("class") or "").lower()
        f = (seat.get_attribute("fill") or "").lower()
        if "select" in c or "active" in c or "chosen" in c:
            return True
        if f and f != before_fill:  # 颜色变了通常表示被选中
            return True
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", seat)
    except Exception:
        pass

    # 招式1：ActionChains 移到元素上真实点击
    try:
        ActionChains(driver).move_to_element(seat).pause(0.1).click().perform()
        if _selected():
            return True
    except Exception as e:
        logging.info("ActionChains 点击异常：%s", e)

    # 招式2：派发完整鼠标事件序列（React 常靠这些）
    try:
        driver.execute_script(
            """
            const el = arguments[0];
            const r = el.getBoundingClientRect();
            const x = r.left + r.width/2, y = r.top + r.height/2;
            for (const t of ['pointerover','pointerenter','pointerdown',
                             'mousedown','pointerup','mouseup','click']) {
              const ev = new MouseEvent(t, {bubbles:true, cancelable:true,
                          view:window, clientX:x, clientY:y});
              el.dispatchEvent(ev);
            }
            """,
            seat,
        )
        if _selected():
            return True
    except Exception as e:
        logging.info("派发事件异常：%s", e)

    # 招式3：兜底，直接 click（万一确实响应）
    try:
        driver.execute_script("arguments[0].click();", seat)
        if _selected():
            return True
    except Exception:
        pass

    return _selected()


# ---- 选数量页：座位选好后确认数量 ----
# 步进器：加号 .nds-e-stepper__incrementButton，输入框 .nds-e-stepper__input
# 订购按钮：EntButton_primary（选够数量前是 disabled）
def set_quantity_and_order(driver, want_count=1, timeout=15):
    """在选数量页把数量加到 want_count 并点「訂購」或「预购」。成功点到返回 True。

    跳转后数量默认0,需要点加号手动加到目标数量。
    """
    import time
    import logging
    from selenium.webdriver.common.by import By

    deadline = time.time() + timeout

    # 第1步:点加号加数量(从0加到want_count)
    logging.info("查找数量加号按钮……")
    time.sleep(0.5)  # 给页面加载时间,从1秒改成0.5秒
    inc_btns = driver.find_elements(By.CSS_SELECTOR, "button.nds-e-stepper__incrementButton, button[class*='incrementButton']")
    if inc_btns:
        logging.info("找到加号按钮,点击%d次", want_count)
        for i in range(want_count):
            try:
                inc = inc_btns[0]
                if inc.get_attribute("disabled"):
                    logging.info("加号按钮disabled,可能已到上限")
                    break
                driver.execute_script("arguments[0].click();", inc)
                logging.info("已点加号第%d次", i+1)
                time.sleep(0.1)  # 从0.3秒改成0.1秒
            except Exception as e:
                logging.info("点加号出错:%s", e)
                break
    else:
        logging.info("未找到加号按钮,跳过数量调整")

    # 第2步:等订购按钮变 enabled 并点击
    logging.info("等待订购按钮可点……")
    found_buttons = []
    while time.time() < deadline:
        btns = driver.find_elements(By.CSS_SELECTOR, "button")
        for btn in btns:
            txt = (btn.text or "").strip()
            is_disabled = btn.get_attribute("disabled")
            cls = btn.get_attribute("class") or ""

            # 记录所有primary按钮
            if "EntButton_primary" in cls or "entButtonGlobal" in cls:
                found_buttons.append((txt, is_disabled))

            # 按钮文字必须含"预购/預購"且带数字(如"预购 1张"),过滤顶部菜单的纯"訂購"
            if (("预购" in txt or "預購" in txt) and any(c.isdigit() for c in txt)) and not is_disabled:
                try:
                    logging.info("找到可点按钮:「%s」", txt)
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    driver.execute_script("arguments[0].click();", btn)
                    logging.info("已点「%s」按钮", txt)
                    return True
                except Exception as e:
                    logging.info("点按钮出错:%s", e)
        time.sleep(0.5)

    logging.info("等了%d秒,页面的primary按钮:%s", timeout, list(set(found_buttons))[:5])
    logging.info("订购按钮一直不可点")
    return False


# ---- 填信息页：手机号 + 勾全部同意（姓名/生日/邮箱由账号自动带，只读） ----
# 手机框 #userPhone；一键同意 .Agreements_agreeAll 里的 checkbox（点 label）。
# 最终「總計…付款」按钮留给用户手点（A 方案：走到这里响铃停手）。
def fill_info_and_agree(driver, phone="", timeout=15):
    """填手机号、勾「同意全部使用條款」。返回 True 表示已就绪等人工付款。"""
    import time
    import logging
    from selenium.webdriver.common.by import By

    deadline = time.time() + timeout

    # 等手机框出现
    while time.time() < deadline:
        if driver.find_elements(By.ID, "userPhone"):
            break
        time.sleep(0.3)

    # 填手机号（可编辑；姓名/生日/邮箱是 readonly，跳过）
    if phone:
        try:
            box = driver.find_element(By.ID, "userPhone")
            box.clear()
            box.send_keys(phone)
            logging.info("已填手机号")
        except Exception as e:
            logging.info("填手机号失败：%s", e)

    # 勾「同意全部使用條款」——点 label 更稳（checkbox 常被样式隐藏）
    try:
        label = driver.find_element(
            By.CSS_SELECTOR, ".Agreements_agreeAll__G2pVc label"
        )
        driver.execute_script("arguments[0].click();", label)
        logging.info("已勾选同意全部条款")
    except Exception as e:
        logging.info("勾同意失败（可能 class 变了）：%s", e)

    return True


# ---- 验证码：图片文字版走 OCR；滑块版返回信号让人工处理 ----
CAPTCHA_TEXT = "text"
CAPTCHA_SLIDER = "slider"
CAPTCHA_NONE = "none"


def detect_captcha(driver):
    """判断当前验证码类型：文字/滑块/无。支持新站和旧站。"""
    from selenium.webdriver.common.by import By

    url = driver.current_url.lower()
    is_old_site = "interpark.com" in url and "nol.com" not in url

    # 旧站:需要在 ifrmSeat 里找验证码
    if is_old_site:
        try:
            driver.switch_to.default_content()
            driver.switch_to.frame("ifrmSeat")

            # 检查验证码div是否显示
            captcha_divs = driver.find_elements(By.ID, "divRecaptcha")
            if len(captcha_divs) > 0 and captcha_divs[0].is_displayed():
                driver.switch_to.default_content()
                return CAPTCHA_TEXT

            # 或者检查imgCaptcha是否显示
            imgs = driver.find_elements(By.ID, "imgCaptcha")
            if len(imgs) > 0 and imgs[0].is_displayed():
                driver.switch_to.default_content()
                return CAPTCHA_TEXT

            driver.switch_to.default_content()
            return CAPTCHA_NONE
        except Exception:
            driver.switch_to.default_content()
            return CAPTCHA_NONE

    # 新站
    if driver.find_elements(By.CSS_SELECTOR, "input[class*='captchaInput']"):
        return CAPTCHA_TEXT
    if driver.find_elements(By.CSS_SELECTOR, "[class*='ModalCaptchaSlider']"):
        return CAPTCHA_SLIDER
    return CAPTCHA_NONE


def _grab_captcha_base64(driver):
    """从 <img alt="Captcha Image"> 的 src 取出 base64（去掉 data: 前缀）。"""
    from selenium.webdriver.common.by import By

    imgs = driver.find_elements(By.CSS_SELECTOR, "img[alt='Captcha Image']")
    if not imgs:
        return None
    src = imgs[0].get_attribute("src") or ""
    if "base64," in src:
        return src.split("base64,", 1)[1]
    return None


def solve_text_captcha(driver, ocr_func, max_try=5):
    """图片文字验证码：读 base64→OCR→填→提交，错了刷新重试。支持新站和旧站。

    ocr_func(base64_str) -> 识别出的字符串（由调用方传入，内部调百度）。
    返回 True 表示验证码弹窗已消失（通过）。
    """
    import time
    import logging
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    url = driver.current_url.lower()
    is_old_site = "interpark.com" in url and "nol.com" not in url

    if is_old_site:
        return _solve_text_captcha_old(driver, ocr_func, max_try)
    else:
        return _solve_text_captcha_new(driver, ocr_func, max_try)


def _solve_text_captcha_new(driver, ocr_func, max_try):
    """新站验证码逻辑。"""
    import time
    import logging
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    for attempt in range(1, max_try + 1):
        b64 = _grab_captcha_base64(driver)
        if not b64:
            logging.info("取不到验证码图片")
            return False
        code = (ocr_func(b64) or "").strip()
        logging.info("验证码 OCR 第%s次：%s", attempt, code)
        if not code:
            _refresh_captcha(driver)
            time.sleep(0.6)
            continue
        try:
            box = driver.find_element(
                By.CSS_SELECTOR, "input[class*='captchaInput']"
            )
            box.clear()
            box.send_keys(code)
            box.send_keys(Keys.ENTER)
        except Exception as e:
            logging.info("填验证码出错：%s", e)
        time.sleep(1.0)
        # 弹窗消失 = 通过
        if detect_captcha(driver) == CAPTCHA_NONE:
            logging.info("验证码通过")
            return True
        # 还在 → 刷新重试
        _refresh_captcha(driver)
        time.sleep(0.6)
    logging.info("验证码多次失败")
    return False


def _solve_text_captcha_old(driver, ocr_func, max_try):
    """旧站验证码逻辑:在 ifrmSeat 里处理。"""
    import time
    import logging
    from selenium.webdriver.common.by import By

    for attempt in range(1, max_try + 1):
        try:
            # 切到 ifrmSeat
            driver.switch_to.default_content()
            driver.switch_to.frame("ifrmSeat")

            # 获取验证码图片
            img = driver.find_element(By.ID, "imgCaptcha")
            img_src = img.get_attribute("src")

            if not img_src or "base64," not in img_src:
                logging.info("验证码图片未加载")
                driver.switch_to.default_content()
                time.sleep(0.5)
                continue

            # OCR识别
            b64 = img_src.split("base64,")[1]
            code = (ocr_func(b64) or "").strip()
            logging.info("验证码 OCR 第%s次：%s", attempt, code)

            if not code or len(code) < 3:
                logging.info("识别结果太短,刷新重试")
                try:
                    refresh_btn = driver.find_element(By.CLASS_NAME, "refreshBtn")
                    refresh_btn.click()
                    time.sleep(0.8)
                except Exception:
                    pass
                driver.switch_to.default_content()
                continue

            # 点击span显示输入框
            try:
                span = driver.find_element(By.CSS_SELECTOR, "div.validationTxt > span.lang")
                driver.execute_script("arguments[0].click();", span)
                time.sleep(0.5)
                logging.info("已点击span显示输入框")
            except Exception as e:
                logging.info("点span失败: %s", e)

            # 输入验证码
            input_box = driver.find_element(By.ID, "txtCaptcha")
            input_box.clear()
            input_box.send_keys(code)
            time.sleep(0.5)

            # 验证输入是否成功
            input_value = input_box.get_attribute("value")
            logging.info("输入框实际值: %s", input_value)

            # 点提交按钮(试多个选择器)
            submit_success = False
            selectors = [
                ("CSS", "div.capchaBtns > a:nth-child(2)"),  # 第2个按钮
                ("CSS", "div.capchaBtns > a:last-child"),    # 最后一个按钮
                ("XPATH", "//div[@class='capchaBtns']//a[contains(text(),'确认') or contains(text(),'确定') or contains(text(),'OK')]"),
            ]

            for sel_type, selector in selectors:
                try:
                    if sel_type == "CSS":
                        btn = driver.find_element(By.CSS_SELECTOR, selector)
                    else:
                        btn = driver.find_element(By.XPATH, selector)

                    btn_text = btn.text or btn.get_attribute("textContent") or ""
                    logging.info("尝试点击按钮: %s (文字:%s)", selector, btn_text.strip())
                    btn.click()
                    submit_success = True
                    logging.info("已提交验证码")
                    break
                except Exception as e:
                    continue

            if not submit_success:
                logging.info("所有提交按钮都点不上")
                driver.switch_to.default_content()
                continue

            time.sleep(2)

            # 检查验证码是否消失
            driver.switch_to.default_content()
            time.sleep(0.5)
            if detect_captcha(driver) == CAPTCHA_NONE:
                logging.info("验证码通过")
                return True

            logging.info("验证码仍存在,可能识别错误或提交失败,重试...")

        except Exception as e:
            logging.info("旧站验证码处理异常: %s", e)
            driver.switch_to.default_content()
            time.sleep(0.5)

    logging.info("验证码多次失败")
    driver.switch_to.default_content()
    return False


def _refresh_captcha(driver):
    from selenium.webdriver.common.by import By

    for btn in driver.find_elements(
        By.CSS_SELECTOR, "button[class*='buttonRefresh']"
    ):
        try:
            driver.execute_script("arguments[0].click();", btn)
            return
        except Exception:
            pass
