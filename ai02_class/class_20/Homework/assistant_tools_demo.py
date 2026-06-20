"""
经典 Function Calling 演示：智能生活助手

本示例同时演示两类工具：
1) qwen_agent 内置工具（无需自己注册，直接在 function_list 里写名字引用）：
   - code_interpreter：Python 代码沙箱，模型可写代码做复杂计算/画图
   - image_gen：文生图，根据文字描述生成图片 URL
   - web_extractor：根据网页 URL 抓取并解析网页正文
2) 外部自定义工具（用 @register_tool 注册，与 exc_sql 同机制）：
   - get_weather       查询城市天气（mock 数据，Function Calling 最经典案例）
   - calculator        安全计算器
   - get_current_time  获取指定时区的当前时间

运行：
    cd ai02_class/class_20/Homework
    <venv>/bin/python assistant_tools_demo.py
需要环境变量 DASHSCOPE_API_KEY。
"""

import os
import json
import math
import random
from datetime import datetime, timezone, timedelta

import dashscope
from qwen_agent.agents import Assistant
from qwen_agent.gui import WebUI
from qwen_agent.tools.base import BaseTool, register_tool

# ====== 配置 DashScope ======
dashscope.api_key = os.getenv('DASHSCOPE_API_KEY', '')
dashscope.timeout = 30


# ====== system prompt ======
system_prompt = """我是一个智能生活助手，可以使用以下工具帮助你：
- get_weather：查询某个城市的天气
- calculator：做数学计算
- get_current_time：获取某个时区的当前时间
- code_interpreter：当问题需要编写并运行 Python 代码（复杂计算、数据处理、画图等）时使用
- image_gen：根据文字描述生成图片（文生图）
- web_extractor：根据网页 URL 抓取网页正文内容

使用原则：
1. 需要实时/具体数据（天气、时间）或精确计算时，必须调用相应工具，不要凭空编造。
2. 简单算术优先用 calculator；需要循环、数组、绘图等复杂逻辑时用 code_interpreter。
3. 用户要画图/生成插画时用 image_gen，并用 markdown 图片语法 ![](URL) 展示结果。
4. 用户给出网址、要求总结或读取网页内容时用 web_extractor。
5. 工具返回结果后，用简洁自然的语言把结论告诉用户。
"""


# ====== 自定义工具 1：天气查询（经典案例，使用 mock 数据）======
@register_tool('get_weather')
class GetWeatherTool(BaseTool):
    description = '查询指定城市的当前天气情况（温度、天气状况、湿度）'
    parameters = [
        {
            'name': 'city',
            'type': 'string',
            'description': '城市名称，例如“北京”、“上海”',
            'required': True,
        },
        {
            'name': 'unit',
            'type': 'string',
            'description': "温度单位，'c'(摄氏) 或 'f'(华氏)，默认摄氏",
            'required': False,
        },
    ]

    def call(self, params: str, **kwargs) -> str:
        args = json.loads(params)
        city = args.get('city', '未知城市')
        unit = str(args.get('unit', 'c')).lower()

        # mock：用城市名做随机种子，保证同一城市每次结果稳定
        rng = random.Random(hash(city) & 0xFFFFFFFF)
        conditions = ['晴', '多云', '阴', '小雨', '雷阵雨', '雾']
        condition = rng.choice(conditions)
        temp_c = rng.randint(-5, 38)
        humidity = rng.randint(30, 95)

        if unit == 'f':
            temp = round(temp_c * 9 / 5 + 32, 1)
            temp_str = f"{temp}°F"
        else:
            temp_str = f"{temp_c}°C"

        return json.dumps({
            'city': city,
            'condition': condition,
            'temperature': temp_str,
            'humidity': f"{humidity}%",
            'note': '（演示数据，非真实天气）',
        }, ensure_ascii=False)


# ====== 自定义工具 2：安全计算器 ======
@register_tool('calculator')
class CalculatorTool(BaseTool):
    description = '计算一个数学表达式，支持 + - * / ** %、括号以及常见数学函数(sin/cos/sqrt/log等)'
    parameters = [
        {
            'name': 'expression',
            'type': 'string',
            'description': "数学表达式字符串，例如 '(3 + 5) * 2'、'sqrt(16) + 2**3'",
            'required': True,
        },
    ]

    def call(self, params: str, **kwargs) -> str:
        args = json.loads(params)
        expr = args.get('expression', '')

        # 只暴露安全的数学函数/常量，禁用内建函数，避免任意代码执行
        allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith('_')}
        allowed.update({'abs': abs, 'round': round, 'min': min, 'max': max, 'pow': pow})
        try:
            result = eval(expr, {'__builtins__': {}}, allowed)
            return json.dumps({'expression': expr, 'result': result}, ensure_ascii=False)
        except Exception as e:
            return f"计算出错: {str(e)}"


# ====== 自定义工具 3：获取当前时间 ======
@register_tool('get_current_time')
class GetCurrentTimeTool(BaseTool):
    description = '获取指定时区的当前日期和时间'
    parameters = [
        {
            'name': 'tz_offset',
            'type': 'string',
            'description': "相对 UTC 的时区偏移小时数，例如北京为 '8'，纽约为 '-5'，默认 '8'",
            'required': False,
        },
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            args = json.loads(params) if params else {}
        except Exception:
            args = {}
        try:
            offset = float(args.get('tz_offset', 8))
        except Exception:
            offset = 8
        tz = timezone(timedelta(hours=offset))
        now = datetime.now(tz)
        return json.dumps({
            'tz': f'UTC{"+" if offset >= 0 else ""}{offset:g}',
            'datetime': now.strftime('%Y-%m-%d %H:%M:%S'),
            'weekday': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][now.weekday()],
        }, ensure_ascii=False)


# ====== 初始化助手 ======
def init_agent_service():
    llm_cfg = {
        'model': 'qwen-max',
        'timeout': 30,
        'retry_count': 3,
        'generate_cfg': {
            'temperature': 0,
            'seed': 1234,
        },
    }
    bot = Assistant(
        llm=llm_cfg,
        name='智能生活助手',
        description='天气/计算/时间 + 代码解释器',
        system_message=system_prompt,
        # 同时挂：3 个自定义工具 + 3 个 qwen_agent 内置工具
        function_list=[
            # 外部自定义工具
            'get_weather', 'calculator', 'get_current_time',
            # qwen_agent 内置工具
            'code_interpreter', 'image_gen', 'web_extractor',
        ],
    )
    print("助手初始化成功！")
    return bot


def app_gui():
    print("正在启动 Web 界面...")
    bot = init_agent_service()
    chatbot_config = {
        'prompt.suggestions': [
            # 自定义工具：get_weather
            '北京今天天气怎么样？',
            '查一下广州的天气，用华氏度显示',
            '深圳和成都现在哪个城市更热？',
            # 自定义工具：calculator
            '帮我算一下 (15 + 27) * 3 - sqrt(144) 等于多少',
            '一个圆半径是 7，面积是多少？',
            '把 88 公斤换算成磅（1 公斤约 2.205 磅）',
            # 自定义工具：get_current_time
            '现在纽约几点了？',
            '伦敦现在是星期几？',
            '北京和东京现在时间差几个小时？',
            # 内置 code_interpreter
            '用代码计算 1 到 100 里所有质数的和，并告诉我有多少个',
            '生成 1 到 50 的随机 20 个数，用代码画出它们的直方图',
            '用代码求斐波那契数列前 20 项',
            # 内置 image_gen（文生图）
            '画一只戴墨镜在沙滩冲浪的柯基犬',
            '生成一张赛博朋克风格的未来城市夜景插画',
            # 内置 web_extractor（抓网页）
            '帮我总结一下这个网页的内容：https://www.baidu.com',
            # 组合：多工具协作
            '先查上海的天气，再用计算器把温度换算成华氏度',
            '现在是几点？再帮我画一张符合当前时段（白天/夜晚）氛围的风景画',
        ]
    }
    print("Web 界面准备就绪，正在启动服务...")
    WebUI(bot, chatbot_config=chatbot_config).run()


if __name__ == '__main__':
    app_gui()
