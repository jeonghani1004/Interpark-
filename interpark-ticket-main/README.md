# Interpark 抢票脚本

自动抢票工具，支持:
- **新站**(nol.com):SVG 座位图
- **旧站**(interpark.com / globalinterpark.com):iframe 座位图

## 使用步骤

### 1. 安装依赖
```bash
pip install selenium pillow requests
```

### 2. 配置 `config.json`

编辑 `config.json`,填入:

```json
{
  "SeatTotal": 1,
  "PhoneNo": "你的手机号",
  "BaiduApiKey": "你的百度API Key",
  "BaiduSecretKey": "你的百度Secret Key"
}
```

**获取百度 OCR API Key**:(验证码自动识别需要)

1. 访问 https://cloud.baidu.com/product/ocr
2. 登录/注册百度云账号
3. 控制台 → 文字识别 OCR → 创建应用
4. 复制 API Key 和 Secret Key 到 config.json

**免费额度**: 每天 500 次调用,足够抢票使用

### 3. 运行

```bash
python gui.py
```

或命令行模式:
```bash
python runner.py
```

## 功能

- ✅ **自动验证码识别**(百度 OCR)
- ✅ **最贵座位优先**(VIP > R Seat > S Seat,按颜色自动识别)
- ✅ **自动填手机号、勾同意条款**
- ✅ **响铃提醒**(完成后)
- ✅ **新旧站自适应**

## 流程

1. 脚本打开 Chrome
2. **你手动**:登录 → 点预订 → 走到验证码弹出
3. 点"接手"按钮
4. 脚本自动:
   - 识别并输入验证码
   - 选座(最贵颜色优先)
   - 填手机号、勾同意条款
   - 响铃提醒
5. **你手动**:付款

## 注意

- **验证码识别需要百度 API Key**,没有 key 时需手动输入
- 旧站(globalinterpark)按座位颜色自动识别:紫色(VIP) > 绿色(R Seat) > 蓝色(S Seat)
- 新站(nol.com)自动选最贵档位座位
- 脚本不会自动付款,需要人工确认后付款

## 常见问题

**Q: 验证码识别失败怎么办?**
A: 检查 config.json 里百度 API Key 是否正确,或手动输入验证码后点"接手"

**Q: 找不到座位?**
A: 可能无票或页面结构变化,把选座页 HTML 发给作者更新

**Q: 旧站怎么只抢 VIP?**
A: 脚本自动按颜色识别,紫色座位优先,没有紫色才选绿色/蓝色
