# 场次配置模板
# 复制本文件为 shows/<你的场次名>.py，填入下面的值，
# 然后在 info.py 里设置 SHOW='<你的场次名>' 即可。

# 商品号：打开 Interpark 详情页，URL 里 prdNo= 后面的数字
PRD_NO = "00000000"
# 展示号：URL 里 dispNo= 后面的值，没有就填 "undefined"
DISP_NO = "undefined"

# 选第几个可选日期（0 = 第一个，1 = 第二个，以此类推）
DATE_INDEX = 1

# 座位图 <area> 的点击顺序。这是该场馆专属的，必须按目标场馆重排。
# 怎么得到：打开选座页，查看 #TmgsTable 下的 <area> 元素，
# 按你想优先抢的区域顺序，把每个区在 area 列表里的序号（从 1 开始）填进来。
list_order = [1, 2, 3]

# 与 list_order 一一对应的区域名，仅用于日志，长度必须和 list_order 相同
list_AreaName = ["区域A", "区域B", "区域C"]
