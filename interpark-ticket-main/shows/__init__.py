"""场次配置包。

每个演出对应 shows/ 下的一个 .py 文件（例如 shows/seventeen.py），
里面定义该场演出的商品号、展示号、日期选择与座位区优先级。
换演出时只需新增一个配置文件并在 info.py 里把 SHOW 指向它，
无须改动 main.py。

一个场次文件需要提供以下变量：

    PRD_NO       str  商品号（Interpark 详情页 URL 里的 prdNo）
    DISP_NO      str  展示号（URL 里的 dispNo，未知填 "undefined"）
    DATE_INDEX   int  选第几个可选日期（0 开始，原脚本固定为 1 即第二个）
    list_order   list 座位图 <area> 元素的点击顺序（该场馆专属）
    list_AreaName list 与 list_order 一一对应的区域名（用于日志）

可选：
    TARGET_URL   str  直接指定抢购页地址，覆盖由 PRD_NO/DISP_NO 拼出的地址
"""

import importlib
import importlib.util
import os
import sys


REQUIRED_FIELDS = ("PRD_NO", "DISP_NO", "DATE_INDEX", "list_order", "list_AreaName")


def _external_shows_dir():
    """exe 同目录下的 shows 文件夹（打包后用户在这里加新场次，无须重新打包）。"""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "shows")


class ShowConfig:
    """把一个场次模块包装成带校验的配置对象。"""

    def __init__(self, module):
        for field in REQUIRED_FIELDS:
            if not hasattr(module, field):
                raise ValueError(
                    f"场次配置 '{module.__name__}' 缺少必填字段: {field}"
                )

        self.name = module.__name__.split(".")[-1]
        self.prd_no = str(module.PRD_NO)
        self.disp_no = str(module.DISP_NO)
        self.date_index = int(module.DATE_INDEX)
        self.list_order = list(module.list_order)
        self.list_AreaName = list(module.list_AreaName)

        if len(self.list_order) != len(self.list_AreaName):
            raise ValueError(
                f"场次配置 '{self.name}' 的 list_order({len(self.list_order)}) "
                f"与 list_AreaName({len(self.list_AreaName)}) 长度不一致"
            )

        # 允许场次文件直接给出完整 URL，否则用 prdNo/dispNo 拼
        self.target_url = getattr(module, "TARGET_URL", None) or (
            "https://www.globalinterpark.com/detail/edetail"
            f"?prdNo={self.prd_no}&dispNo={self.disp_no}"
        )


def load(show_name):
    """按名字加载 shows/<show_name>.py 并返回 ShowConfig。"""
    if not show_name:
        raise ValueError("未指定场次：请填写 SHOW='<场次文件名>'")

    # 优先读 exe/项目 同目录 shows/ 下的外部文件（方便加新场次不重打包）
    ext_path = os.path.join(_external_shows_dir(), f"{show_name}.py")
    if os.path.exists(ext_path):
        spec = importlib.util.spec_from_file_location(f"shows.{show_name}", ext_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return ShowConfig(module)

    # 否则读打包进来的内置场次
    try:
        module = importlib.import_module(f"shows.{show_name}")
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            f"找不到场次配置 shows/{show_name}.py（SHOW='{show_name}'）"
        ) from e
    return ShowConfig(module)
