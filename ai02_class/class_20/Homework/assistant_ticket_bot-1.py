import os
import random
from datetime import datetime, timedelta

import dashscope
import pandas as pd
from sqlalchemy import create_engine, text
from qwen_agent.agents import Assistant
from qwen_agent.gui import WebUI
from qwen_agent.tools.base import BaseTool, register_tool

# ====== 基础配置 ======
# 本地 SQLite 数据库文件路径（与本脚本同目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'tkt_orders.db')
DB_URL = f'sqlite:///{DB_PATH}'

# 图表（ECharts/pyecharts）输出目录
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# 配置 DashScope
dashscope.api_key = os.getenv('DASHSCOPE_API_KEY', '')  # 从环境变量获取 API Key
dashscope.timeout = 30  # 设置超时时间为 30 秒


# ====== 门票助手 system prompt 和函数描述 ======
# 注意：运行环境改为 SQLite，日期函数与 MySQL 略有不同（如按周用 strftime('%Y-%W', order_time)）
system_prompt = """我是门票助手，以下是关于门票订单表相关的字段，我可能会编写对应的SQL(运行环境是SQLite)，对数据进行查询
-- 门票订单表
CREATE TABLE tkt_orders (
    order_time DATETIME,             -- 订单日期
    account_id INT,                  -- 预定用户ID
    gov_id VARCHAR(18),              -- 商品使用人ID（身份证号）
    gender VARCHAR(10),              -- 使用人性别
    age INT,                         -- 年龄
    province VARCHAR(30),           -- 使用人省份
    SKU VARCHAR(100),                -- 商品SKU名
    product_serial_no VARCHAR(30),  -- 商品ID
    eco_main_order_id VARCHAR(20),  -- 订单ID
    sales_channel VARCHAR(20),      -- 销售渠道
    status VARCHAR(30),             -- 商品状态
    order_value DECIMAL(10,2),       -- 订单金额
    quantity INT                     -- 商品数量
);
一日门票，对应多种SKU：
Universal Studios Beijing One-Day Dated Ticket-Standard
Universal Studios Beijing One-Day Dated Ticket-Child
Universal Studios Beijing One-Day Dated Ticket-Senior
二日门票，对应多种SKU：
USB 1.5-Day Dated Ticket Standard
USB 1.5-Day Dated Ticket Discounted
一日门票、二日门票查询
SUM(CASE WHEN SKU LIKE 'Universal Studios Beijing One-Day%' THEN quantity ELSE 0 END) AS one_day_ticket_sales,
SUM(CASE WHEN SKU LIKE 'USB%' THEN quantity ELSE 0 END) AS two_day_ticket_sales
重要：运行环境是 SQLite，请使用 SQLite 语法。
- 按年月分组：strftime('%Y-%m', order_time)
- 按周分组：strftime('%Y-%W', order_time)
- 日期范围筛选：order_time >= '2023-07-01' AND order_time < '2023-08-01'
我将回答用户关于门票相关的问题。
当用户需要图表/可视化（如柱状图、折线图、饼图）时，我会先用 exc_sql 查询数据，
再调用 plot_chart 工具进行绘图：x_data 为类目；当只有一个指标时用 y_data；
当有多个指标（如“一日票销量”和“二日票销量”）时，使用 series 传多系列，
格式为 [{"name":"一日票","data":[...]},{"name":"二日票","data":[...]}]，
这样会绘制多色分组柱状图，颜色更丰富。
"""


# ====== mock 数据生成 ======
# 各 SKU 及其单价（用于生成合理的订单金额）
SKU_PRICES = {
    'Universal Studios Beijing One-Day Dated Ticket-Standard': 528.0,
    'Universal Studios Beijing One-Day Dated Ticket-Child': 396.0,
    'Universal Studios Beijing One-Day Dated Ticket-Senior': 396.0,
    'USB 1.5-Day Dated Ticket Standard': 749.0,
    'USB 1.5-Day Dated Ticket Discounted': 560.0,
}

# 商品ID（与 SKU 一一对应）
SKU_SERIAL = {
    'Universal Studios Beijing One-Day Dated Ticket-Standard': 'PID-1D-STD',
    'Universal Studios Beijing One-Day Dated Ticket-Child': 'PID-1D-CHD',
    'Universal Studios Beijing One-Day Dated Ticket-Senior': 'PID-1D-SEN',
    'USB 1.5-Day Dated Ticket Standard': 'PID-15D-STD',
    'USB 1.5-Day Dated Ticket Discounted': 'PID-15D-DIS',
}

PROVINCES = [
    '北京', '天津', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江',
    '上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南',
    '湖北', '湖南', '广东', '广西', '海南', '重庆', '四川', '贵州',
    '云南', '陕西', '甘肃', '青海', '宁夏', '新疆',
]

SALES_CHANNELS = ['官网', '旅行社', 'OTA', '线下门店', '小程序', '飞猪']
STATUSES = ['已使用', '未使用', '已退款', '已过期']


def generate_mock_data(n: int = 500, seed: int = 1234) -> pd.DataFrame:
    """根据建表结构生成 n 条 mock 门票订单数据。"""
    random.seed(seed)

    start = datetime(2023, 1, 1)
    end = datetime(2023, 12, 31, 23, 59, 59)
    total_seconds = int((end - start).total_seconds())

    skus = list(SKU_PRICES.keys())
    rows = []
    for i in range(n):
        sku = random.choice(skus)
        quantity = random.randint(1, 5)
        price = SKU_PRICES[sku]
        order_value = round(price * quantity, 2)

        order_time = start + timedelta(seconds=random.randint(0, total_seconds))

        # 根据 SKU 让年龄更贴近语义（Child 偏小、Senior 偏大）
        if sku.endswith('Child'):
            age = random.randint(3, 14)
        elif sku.endswith('Senior'):
            age = random.randint(60, 85)
        else:
            age = random.randint(15, 65)

        gender = random.choice(['男', '女'])
        # 简单 mock 一个 18 位身份证号（仅用于占位，非真实校验）
        gov_id = f"{random.randint(110000, 659000)}{order_time.year}{random.randint(1000, 9999)}{random.randint(1000, 9999)}"

        rows.append({
            'order_time': order_time.strftime('%Y-%m-%d %H:%M:%S'),
            'account_id': random.randint(10000, 99999),
            'gov_id': gov_id[:18],
            'gender': gender,
            'age': age,
            'province': random.choice(PROVINCES),
            'SKU': sku,
            'product_serial_no': SKU_SERIAL[sku],
            'eco_main_order_id': f"ECO{order_time.strftime('%Y%m%d')}{i:05d}",
            'sales_channel': random.choice(SALES_CHANNELS),
            'status': random.choice(STATUSES),
            'order_value': order_value,
            'quantity': quantity,
        })

    return pd.DataFrame(rows)


def init_database(force: bool = False) -> None:
    """初始化本地 SQLite 数据库：建表并写入 500 条 mock 数据。

    - 若表已存在且有数据，则跳过（除非 force=True）。
    """
    engine = create_engine(DB_URL)
    need_seed = True
    if not force:
        try:
            with engine.connect() as conn:
                result = conn.execute(text('SELECT COUNT(*) FROM tkt_orders'))
                count = result.scalar()
                if count and count > 0:
                    need_seed = False
                    print(f"数据库已存在 {count} 条数据，跳过初始化。({DB_PATH})")
        except Exception:
            need_seed = True

    if need_seed:
        df = generate_mock_data(500)
        df.to_sql('tkt_orders', engine, if_exists='replace', index=False)
        print(f"已生成 500 条 mock 数据并写入：{DB_PATH}")


# ====== exc_sql 工具类实现 ======
@register_tool('exc_sql')
class ExcSQLTool(BaseTool):
    """
    SQL查询工具，执行传入的SQL语句并返回结果（本地 SQLite）。
    """
    description = '对于生成的SQL，进行SQL查询'
    parameters = [{
        'name': 'sql_input',
        'type': 'string',
        'description': '生成的SQL语句',
        'required': True
    }]

    def call(self, params: str, **kwargs) -> str:
        import json
        args = json.loads(params)
        sql_input = args['sql_input']
        # 连接本地 SQLite 数据库
        engine = create_engine(DB_URL)
        try:
            df = pd.read_sql(sql_input, engine)
            # 返回前10行，防止数据过多
            return df.head(10).to_markdown(index=False)
        except Exception as e:
            return f"SQL执行出错: {str(e)}"


# ====== plot_chart 绘图工具（基于百度 ECharts / pyecharts）======
@register_tool('plot_chart')
class PlotChartTool(BaseTool):
    """
    图表绘制工具：使用百度 ECharts（pyecharts）将数据绘制为柱状图/折线图/饼图，
    截图为 PNG 并以 Markdown 图片形式直接嵌入聊天界面显示。
    """
    description = (
        '使用百度 ECharts 绘制图表。当用户需要可视化（柱状图/折线图/饼图）时调用。'
        '通常先用 exc_sql 查询数据，再把数据传入本工具绘图。'
    )
    parameters = [
        {
            'name': 'chart_type',
            'type': 'string',
            'description': "图表类型，可选值：'bar'(柱状图)、'line'(折线图)、'pie'(饼图)",
            'required': True,
        },
        {
            'name': 'title',
            'type': 'string',
            'description': '图表标题',
            'required': True,
        },
        {
            'name': 'x_data',
            'type': 'string',
            'description': "X轴类目数组的JSON字符串，例如 '[\"北京\",\"上海\",\"广东\"]'；饼图时为每个扇区的名称",
            'required': True,
        },
        {
            'name': 'series',
            'type': 'string',
            'description': (
                "多系列数据的JSON字符串（推荐）。格式为对象数组，每个对象含 name 和 data，"
                "每个 data 与 x_data 一一对应。"
                "例如 '[{\"name\":\"一日票\",\"data\":[10,20,30]},{\"name\":\"二日票\",\"data\":[5,8,12]}]'。"
                "若只有单系列，可改用 y_data。"
            ),
            'required': False,
        },
        {
            'name': 'y_data',
            'type': 'string',
            'description': "单系列时使用：Y轴数值数组的JSON字符串，例如 '[120, 88, 200]'；需与 x_data 一一对应。提供 series 时可忽略本参数",
            'required': False,
        },
        {
            'name': 'series_name',
            'type': 'string',
            'description': '单系列时的系列名称（图例显示），例如 “入园人数”',
            'required': False,
        },
    ]

    def call(self, params: str, **kwargs) -> str:
        import json

        from pyecharts.charts import Bar, Line, Pie
        from pyecharts import options as opts

        try:
            args = json.loads(params)
        except Exception as e:
            return f"参数解析失败: {str(e)}"

        chart_type = str(args.get('chart_type', 'bar')).lower()
        title = args.get('title', '图表')
        series_name = args.get('series_name', '数值')

        # 丰富的调色板（多系列 / 多扇区 / 单系列多色柱子都会用到）
        palette = [
            '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
            '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#ff9f7f',
            '#37a2da', '#ffdb5c', '#9fe6b8', '#e062ae', '#e690d1',
        ]

        # x_data / y_data 可能是 JSON 字符串，也可能已经是列表，做兼容处理
        def _to_list(v):
            if isinstance(v, list):
                return v
            try:
                return json.loads(v)
            except Exception:
                return [s.strip() for s in str(v).split(',') if s.strip()]

        x_data = _to_list(args.get('x_data', []))
        if not x_data:
            return "绘图失败：x_data 为空。"

        # 统一解析多系列：优先使用 series，否则回退到单系列 (y_data + series_name)
        raw_series = args.get('series')
        series_list = []
        if raw_series:
            parsed = raw_series if isinstance(raw_series, list) else json.loads(raw_series)
            for s in parsed:
                name = s.get('name', '数值')
                data = _to_list(s.get('data', []))
                series_list.append({'name': name, 'data': data})
        else:
            y_data = _to_list(args.get('y_data', []))
            if not y_data:
                return "绘图失败：未提供 series，也未提供 y_data。"
            series_list.append({'name': series_name, 'data': y_data})

        # 校验每个系列数据长度
        for s in series_list:
            if len(s['data']) != len(x_data):
                return (f"绘图失败：系列“{s['name']}”的数据长度({len(s['data'])}) "
                        f"与 x_data({len(x_data)}) 不一致。")

        try:
            if chart_type == 'pie':
                # 饼图只取第一个系列，每个扇区自动用调色板不同颜色
                first = series_list[0]
                chart = (
                    Pie()
                    .add(first['name'], [list(z) for z in zip(x_data, first['data'])])
                    .set_colors(palette)
                    .set_global_opts(
                        title_opts=opts.TitleOpts(title=title),
                        legend_opts=opts.LegendOpts(type_='scroll', pos_top='8%'),
                    )
                    .set_series_opts(label_opts=opts.LabelOpts(formatter='{b}: {c} ({d}%)'))
                )
            elif chart_type == 'line':
                chart = Line().add_xaxis([str(x) for x in x_data])
                for s in series_list:
                    chart.add_yaxis(s['name'], s['data'], is_smooth=True)
                chart.set_colors(palette)
                chart.set_global_opts(
                    title_opts=opts.TitleOpts(title=title, pos_left='center'),
                    xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=30)),
                    legend_opts=opts.LegendOpts(type_='scroll', pos_top='8%'),
                )
            else:  # 默认柱状图
                chart = Bar().add_xaxis([str(x) for x in x_data])
                if len(series_list) == 1:
                    # 单系列：每根柱子用不同颜色，让画面更丰富
                    s = series_list[0]
                    bar_items = [
                        opts.BarItem(
                            name=str(x_data[i]),
                            value=v,
                            itemstyle_opts=opts.ItemStyleOpts(color=palette[i % len(palette)]),
                        )
                        for i, v in enumerate(s['data'])
                    ]
                    chart.add_yaxis(s['name'], bar_items)
                else:
                    # 多系列：分组柱状图，每个系列一种颜色
                    for s in series_list:
                        chart.add_yaxis(s['name'], s['data'])
                    chart.set_colors(palette)
                chart.set_global_opts(
                    title_opts=opts.TitleOpts(title=title, pos_left='center'),
                    xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=30)),
                    legend_opts=opts.LegendOpts(type_='scroll', pos_top='8%'),
                )

            # 渲染为 HTML 文件
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            base = f'chart_{chart_type}_{ts}'
            html_path = os.path.join(CHARTS_DIR, base + '.html')
            png_path = os.path.join(CHARTS_DIR, base + '.png')
            chart.render(html_path)

            # 用无头 Chrome 把 ECharts 截图为 PNG，便于直接嵌入聊天界面
            from pyecharts.render import make_snapshot
            from snapshot_selenium import snapshot
            # delay 调大，确保 ECharts 的 JS（从 CDN 加载）渲染完成后再截图，
            # 否则可能出现 "echarts is not defined"
            make_snapshot(snapshot, html_path, png_path, delay=4, is_remove_html=False)

            cn_type = {'bar': '柱状图', 'line': '折线图', 'pie': '饼图'}.get(chart_type, '图表')
            # 返回 Markdown 图片，WebUI 会把 PNG 直接渲染在聊天框内
            return f"已使用百度 ECharts 生成{cn_type}《{title}》：\n\n![{title}]({png_path})"
        except Exception as e:
            return f"绘图出错: {str(e)}"


# ====== 初始化门票助手服务 ======
def init_agent_service():
    """初始化门票助手服务"""
    llm_cfg = {
        'model': 'qwen-max',
        'timeout': 30,
        'retry_count': 3,
        'generate_cfg': {
            'temperature': 0,
            'seed': 1234,      # 固定随机种子，进一步增强可复现性
        },
    }
    try:
        bot = Assistant(
            llm=llm_cfg,
            name='门票助手',
            description='门票查询与订单分析',
            system_message=system_prompt,
            function_list=['exc_sql', 'plot_chart'],  # 只传工具名字符串
        )
        print("助手初始化成功！")
        return bot
    except Exception as e:
        print(f"助手初始化失败: {str(e)}")
        raise


def app_tui():
    """终端交互模式"""
    try:
        bot = init_agent_service()
        messages = []
        while True:
            try:
                query = input('user question: ')
                file = input('file url (press enter if no file): ').strip()
                if not query:
                    print('user question cannot be empty！')
                    continue
                if not file:
                    messages.append({'role': 'user', 'content': query})
                else:
                    messages.append({'role': 'user', 'content': [{'text': query}, {'file': file}]})

                print("正在处理您的请求...")
                response = []
                for response in bot.run(messages):
                    print('bot response:', response)
                messages.extend(response)
            except Exception as e:
                print(f"处理请求时出错: {str(e)}")
                print("请重试或输入新的问题")
    except Exception as e:
        print(f"启动终端模式失败: {str(e)}")


def app_gui():
    """图形界面模式，提供 Web 图形界面"""
    try:
        print("正在启动 Web 界面...")
        bot = init_agent_service()
        chatbot_config = {
            'prompt.suggestions': [
                # 销量 / 时间趋势
                '2023年4、5、6月一日门票，二日门票的销量多少？帮我按照周进行统计',
                '2023年全年每个月的订单总金额和订单数量分别是多少？',
                '统计2023年各季度一日票和二日票的销量对比',
                '2023年哪个月的销售额最高？列出销售额排名前3的月份',
                # 地域分析
                '2023年7月的不同省份的入园人数统计',
                '2023年全年入园人数最多的前10个省份是哪些？',
                # 渠道分析
                '帮我查看2023年10月1-7日销售渠道订单金额排名',
                '统计各销售渠道的订单数量、总金额及平均客单价',
                # 商品 / SKU 分析
                '各SKU的销量和销售额分别是多少？按销售额从高到低排序',
                '一日票和二日票的总销量、总销售额各是多少？占比如何？',
                # 用户画像
                '按性别统计购票人数和总消费金额',
                '统计不同年龄段（0-17、18-30、31-50、51岁以上）的购票人数',
                # 订单状态
                '统计各订单状态（已使用/未使用/已退款/已过期）的订单数量和金额',
                '2023年的退款订单一共有多少笔？退款总金额是多少？',
                # 图表可视化（百度 ECharts）
                '统计全年入园人数前10的省份，并用柱状图展示',
                '统计各销售渠道的订单金额占比，并画成饼图',
                '统计2023年每个月的订单总金额，并用折线图展示趋势',
            ]
        }
        print("Web 界面准备就绪，正在启动服务...")
        WebUI(
            bot,
            chatbot_config=chatbot_config
        ).run(server_port=7860)
    except Exception as e:
        print(f"启动 Web 界面失败: {str(e)}")
        print("请检查网络连接和 API Key 配置")


if __name__ == '__main__':
    # 启动前先初始化本地 SQLite 数据库（建表 + mock 500 条）
    init_database()
    # 运行模式选择
    app_gui()          # 图形界面模式（默认）
