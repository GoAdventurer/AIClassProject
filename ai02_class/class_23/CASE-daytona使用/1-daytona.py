from daytona import Daytona, DaytonaConfig
import os

# 定义配置
config = DaytonaConfig(api_key=os.getenv("DAYTONA_API_KEY"))

# 初始化 Daytona 客户端
daytona = Daytona(config)

# 创建沙箱实例
sandbox = daytona.create()

# 在沙箱中安全地运行代码
response = sandbox.process.code_run('print("Hello World from code!")')
if response.exit_code != 0:
  print(f"错误: {response.exit_code} {response.result}")
else:
    print(response.result)
