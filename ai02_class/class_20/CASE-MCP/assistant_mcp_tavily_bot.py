"""基于 Assistant 实现的 Tavily 搜索智能助手

这个模块提供了一个智能搜索助手，可以：
1. 通过自然语言进行网络搜索查询
2. 支持多种交互方式（GUI、TUI、测试模式）
3. 支持新闻搜索、信息检索、内容提取等功能
"""

import os
from typing import Optional
import dashscope
from qwen_agent.agents import Assistant
from qwen_agent.gui import WebUI

# 定义资源文件根目录
ROOT_RESOURCE = os.path.join(os.path.dirname(__file__), 'resource')

# 配置 DashScope
dashscope.api_key = os.getenv('DASHSCOPE_API_KEY', '')  # 从环境变量获取 API Key
dashscope.timeout = 30  # 设置超时时间为 30 秒

def init_agent_service():
    """初始化 Tavily 搜索助手服务
    
    配置说明：
    - 使用 qwen-max 作为底层语言模型
    - 设置系统角色为搜索助手
    - 配置 Tavily MCP 工具
    
    Returns:
        Assistant: 配置好的搜索助手实例
    """
    # LLM 模型配置
    llm_cfg = {
        'model': 'qwen-max',
        'timeout': 30,  # 设置模型调用超时时间
        'retry_count': 3,  # 设置重试次数
    }
    # 系统角色设定
    system = ('你扮演一个搜索助手，你具有网络搜索、信息检索、内容提取等能力。'
             '你可以帮助用户搜索新闻、查找信息、提取网页内容等。'
             '你应该充分利用 Tavily 搜索的各种功能来提供专业的建议。')
    # MCP 工具配置
    tools = [{
        "mcpServers": {
            "tavily-mcp": {
                "command": "npx",
                "args": [
                    "-y",
                    "tavily-mcp@0.1.4"
                ],
                "autoApprove": [],
                "disabled": False,
                "env": {
                    "TAVILY_API_KEY": os.getenv('TAVILY_API_KEY', 'your-api-key-here')
                }
            }
        }
    }]
    
    try:
        # 创建助手实例
        bot = Assistant(
            llm=llm_cfg,
            name='搜索助手',
            description='网络搜索与信息检索',
            system_message=system,
            function_list=tools,
        )
        print("助手初始化成功！")
        return bot
    except Exception as e:
        print(f"助手初始化失败: {str(e)}")
        raise

def app_gui():
    """图形界面模式
    
    提供 Web 图形界面，特点：
    - 友好的用户界面
    - 预设查询建议
    - 智能搜索功能
    """
    try:
        print("正在启动 Web 界面...")
        # 初始化助手
        bot = init_agent_service()
        # 配置聊天界面
        chatbot_config = {
            'prompt.suggestions': [
                '查找黄金相关的新闻',
                '搜索最新的AI技术发展趋势',
                '查找2026年经济预测相关文章',
                '搜索Python编程最佳实践',
                '查找最新的科技产品发布信息',
                '搜索健康饮食相关的最新研究',
                '查找加密货币市场最新动态',
                '搜索旅游目的地推荐',
                '查找股票市场分析报告',
                '搜索环保和可持续发展相关新闻'
            ]
        }
        
        print("Web 界面准备就绪，正在启动服务...")
        # 启动 Web 界面
        WebUI(
            bot,
            chatbot_config=chatbot_config
        ).run()
    except Exception as e:
        print(f"启动 Web 界面失败: {str(e)}")
        print("请检查网络连接和 API Key 配置")


if __name__ == '__main__':
    # 运行模式选择
    app_gui()          # 图形界面模式（默认）