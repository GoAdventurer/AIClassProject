# 深思熟虑型投研助手：LangGraph 版 vs qwen_agent 版 对比笔记

两个文件实现的是**同一个「深思熟虑型」智能投研助手**（感知 → 建模 → 推理 → 决策 → 报告，五阶段），
但分别用了两套完全不同的框架思路。

- `deliberative_research_langgraph.py`（540 行）—— 基于 **LangGraph**
- `deliberative_research_qwen_agent.py`（1135 行）—— 基于 **qwen_agent**

---

## 一、最核心的区别：谁来「编排」流程

|              | LangGraph 版            | qwen_agent 版              |
| ------------ | ----------------------- | -------------------------- |
| **编排者**   | **代码**（开发者画好的状态图） | **大模型**（自己决定调哪个工具） |
| 流程性质     | 确定性、固定顺序        | 涌现式、模型自主决定       |
| 本质范式     | 显式状态机 / 工作流     | Function Calling / 工具自主调用 |

这是两者的根本分野：

- **LangGraph**：五个阶段是图里的**节点（node）**，开发者用 `add_edge` 把它们**写死**成
  `perception → modeling → reasoning → decision → report → END`。
  模型只在每个节点里被调用一次填内容，**走哪条路是代码说了算**。
- **qwen_agent**：五个阶段是注册的**工具（@register_tool）**，开发者只把它们交给 `Assistant`，
  **调用顺序由大模型根据 system_prompt 自己决定**（甚至有个 `complete_analysis` 让模型一步做完）。

---

## 二、逐项对比

### 1. 框架 / LLM 接入

- **LangGraph 版**：用 LangChain 的 `Tongyi`（**补全式 LLM**）+ `StateGraph`。
  ```python
  from langchain_community.llms import Tongyi
  llm = Tongyi(model_name="qwen-max", dashscope_api_key=DASHSCOPE_API_KEY)
  ```
- **qwen_agent 版**：用 `Assistant`（**对话式 + 自带 function calling**）+ `dashscope`。

### 2. 流程定义方式

- **LangGraph** —— 显式建图（边写死）：
  ```python
  workflow.add_edge("perception", "modeling")
  workflow.add_edge("modeling", "reasoning")
  workflow.add_edge("reasoning", "decision")
  workflow.add_edge("decision", "report")
  workflow.add_edge("report", END)
  ```
- **qwen_agent** —— 只列工具，顺序交给模型：
  ```python
  function_list=['market_perception', 'market_modeling',
                 'investment_reasoning', 'investment_decision', 'generate_report']
  ```

### 3. 状态 / 记忆管理

- **LangGraph**：用一个 `TypedDict`（`ResearchAgentState`）作为**全局状态**，在节点间**显式传递**。
  每个节点 `return {**state, ...}` 更新它。阶段数据天然串联，类型清晰。
- **qwen_agent**：工具本身是**无状态**的，靠一个全局字典 `_last_analysis_dict` + `session_id`
  **手动存中间结果**，跨工具调用时再取出来（弥补「工具间不共享状态」的问题）。

### 4. 结构化输出

- **LangGraph**：为每阶段定义 **Pydantic 模型**（`PerceptionOutput` 等）+ `JsonOutputParser`，
  强约束 LLM 输出 JSON 再解析。
- **qwen_agent**：用**工具参数 schema**（`parameters=[...]`）描述入参；输出是工具里**拼好的 Markdown 文本**。

### 5. 数据从哪来（隐蔽但重要）

- **LangGraph**：每阶段内容**真的由 LLM 生成**（prompt 让模型扮演分析师产出市场数据）。
- **qwen_agent**：工具里大量是**写死的模板 / mock 数据**（f-string 拼的 GDP、CPI 等固定值），
  LLM 主要负责「编排 + 串讲」，真正的分析内容反而更套路化。

### 6. 交互界面

- **LangGraph**：命令行 `input()`，跑完把报告存成 txt。
- **qwen_agent**：默认 `WebUI()` **网页界面**（开箱即用），也有 `app_tui` 终端模式。

### 7. 代码量

- LangGraph **540 行** vs qwen_agent **1135 行**。
  后者翻倍，主要因为每个工具都要写完整的 `parameters` schema、`call` 实现、mock 数据，
  外加一个大而全的 `complete_analysis` 和报告模板。

---

## 三、一句话总结 & 选型建议

```
LangGraph  = 把「怎么想」写进代码    → 流程可控、可预测、易调试、好加分支/循环/回退
qwen_agent = 把「怎么想」交给模型    → 灵活、对话式、自带 WebUI，但流程不可控、靠 prompt 约束
```

- 想要**严格、可复现的多步分析管线**（尤其有条件分支、循环、错误重试）→ **LangGraph**。
  本例那个 `router` / `current_phase` 的错误回退机制就是这种思路。
- 想要**快速搭一个能聊天、自己挑工具的助手**，且能直接给个网页 → **qwen_agent**。

> 有意思的是：本例两者其实都是「线性五步」，所以 LangGraph 的图能力没完全发挥；
> 而 qwen_agent 把线性流程交给模型，反而带来了「模型可能跳步 / 乱序」的不确定性
> —— 这恰好反映了两种范式的取舍。

---

## 四、速查表

| 维度         | LangGraph 版                    | qwen_agent 版                       |
| ------------ | ------------------------------- | ----------------------------------- |
| 框架         | LangGraph (`StateGraph`)        | qwen_agent (`Assistant` + `WebUI`)  |
| LLM 封装     | `Tongyi`（补全式）              | `dashscope` + 内置 function calling |
| 五阶段是     | 图的节点（node）                | 注册的工具（@register_tool）        |
| 流程控制     | 代码写死的边（确定性）          | 模型自主决定（涌现式）              |
| 状态管理     | `TypedDict` 显式传递            | 全局 dict + `session_id` 手动存     |
| 结构化输出   | Pydantic + `JsonOutputParser`   | 工具 `parameters` schema            |
| 内容来源     | LLM 真实生成                    | 工具内 mock / 模板                  |
| 交互界面     | CLI（`input()`）                | WebUI 网页（默认）                  |
| 代码量       | 540 行                          | 1135 行                             |
| 适用场景     | 可控、复杂、可复现的多步管线    | 灵活、对话式、快速搭建带 UI 的助手  |
