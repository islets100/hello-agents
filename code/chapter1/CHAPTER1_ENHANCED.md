# 智能旅行助手 v2 — 记忆 + 售罄备选 + 反思增强

> 基于 Chapter 1 原始 ReAct 架构的三项功能增强

---

## 一、架构总览：双层循环

```
┌────────────────────────────────────────────────────────┐
│                   外层循环（对话层）                      │
│  while True:                                           │
│    用户输入 → 拒绝检测 → [3次则反思] → ReAct 推理       │
│                                                         │
│  PreferenceMemory ─── 每次 ReAct 调用前注入到 System    │
│  rejection_counter ── 连续拒绝达到3次触发反思            │
└────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│                   内层循环（ReAct 层）                    │
│  for step in range(5):                                 │
│    Thought → Action → Observation → ...                │
│                                                         │
│  可用工具:                                             │
│    get_weather(city)           ← 原有                   │
│    get_attraction(city,weather) ← 原有                   │
│    check_ticket_availability() ← 新增                    │
│    update_memory()             ← 新增                    │
└────────────────────────────────────────────────────────┘
```

### 关键设计点

| 层次 | 职责 | 终止条件 |
|------|------|---------|
| **外层对话层** (`main()`) | 获取用户输入、检测拒绝、触发反思、调用内层 | 用户输入 `exit` |
| **内层 ReAct 层** (`run_react_cycle()`) | Thought→Action→Observation 循环 | `Finish[...]` 或 达到 5 步上限 |

**没有引入新架构**。原代码本身就是 ReAct（Thought → Action → Observation），三个新功能都是在这一框架内通过「增加工具 + 增强循环逻辑」实现的。

---

## 二、功能一：偏好记忆

### 2.1 设计思路

用户在与智能体的多轮对话中，会透露出个人偏好（"我喜欢历史文化"、"预算有限"）。传统 ReAct 没有长期记忆，每轮对话都是独立的。我们**新增了一个 `PreferenceMemory` 类**，在每轮 ReAct 推理前将记忆注入到 System Prompt 中。

### 2.2 实现

```python
class PreferenceMemory:
    def __init__(self):
        self.likes = set()       # 喜欢的类型
        self.dislikes = set()    # 不喜欢的类型
        self.budget = None       # 预算范围
        self.travel_style = None # 出行风格

    def update(self, key: str, value: str) -> str:
        """由 LLM 在推理过程中主动调用"""
        # key: like / dislike / budget / travel_style
        self.likes.add(value)  # set 自带去重

    def to_context(self) -> str:
        """生成注入到 System Prompt 的字符串"""
        # 格式如:
        # ---
        # 📋 用户偏好记忆（请参考）
        # - 👍 用户喜欢的类型: 历史文化
        # - 👎 用户不喜欢的类型: 太贵
        # ---
```

### 2.3 记忆注入时机

在 `run_react_cycle()` 的**每一步** ReAct 推理之前调用：

```python
# 构建完整 Prompt = 对话历史 + 偏好记忆上下文
conversation = "\n".join(prompt_history)
memory_context = memory.to_context()  # ← 注入记忆
full_prompt = conversation + memory_context

# 调用 LLM
llm_output = llm_client.generate(full_prompt, system_prompt=AGENT_SYSTEM_PROMPT)
```

### 2.4 LLM 如何「学会」记录偏好？

不需要额外训练。我们做了两件事：

1. **在 System Prompt 中声明了 `update_memory` 工具**，LLM 知道它可以调用
2. **在 System Prompt 中加入指令**："当用户表达了明确的喜好或厌恶时，及时调用 update_memory 记录下来"

当 LLM 在对话中看到用户说"我不喜欢爬山"时，它会在接下来的 ReAct 步骤中自动调用：
```
Thought: 用户不喜欢爬山，我应该记录这个偏好
Action: update_memory(key="dislike", value="爬山")
```

---

## 三、功能二：门票售罄 → 自动备选

### 3.1 设计思路

这是 ReAct 模式**天然支持**的场景。不需要特殊逻辑，只需要：

1. 新增一个 `check_ticket_availability(attraction)` 工具
2. 在 System Prompt 中声明规则："如果 Observation 显示门票已售罄，请自动推荐替代景点"

ReAct 循环会自动处理：

```
Thought: 故宫不错，先检查门票
Action: check_ticket_availability(attraction="故宫博物院")
Observation: 很抱歉，故宫博物院的门票已售罄。

Thought: 故宫已售罄，用户喜欢历史文化→推荐天坛或颐和园
Action: get_attraction(city="北京", weather="晴")
```

### 3.2 实现

```python
# 模拟已售罄的热门景点
SOLD_OUT_ATTRACTIONS = {"故宫博物院", "上海迪士尼乐园", "北京环球影城", "秦始皇兵马俑"}

def check_ticket_availability(attraction: str) -> str:
    if attraction in SOLD_OUT_ATTRACTIONS:
        return f"很抱歉，{attraction}的门票已售罄。建议您考虑其他相似景点。"
    return f"好消息！{attraction}的门票可以购买。"
```

### 3.3 为什么不需要额外分支代码？

**关键在于 ReAct 的 Observation → Thought 闭环**。工具返回的"已售罄"信息成为 Observation，LLM 在下一个 Thought 中自然会思考替代方案。不需要我们在 Python 代码中写 if-else。

---

## 四、功能三：3 次拒绝后反思

### 4.1 设计思路

这是三个功能中最复杂的。它发生在**外层对话层**，而非内层 ReAct 层。

流程：
```
用户第1次拒绝 → rejection_count = 1, 记录原因
用户第2次拒绝 → rejection_count = 2, 记录原因
用户第3次拒绝 → rejection_count = 3 → 🚨 触发反思
                   ↓
           构建反思 Prompt → 单独调用 LLM → 输出反思结果
                   ↓
           重置计数器 → 继续对话
```

### 4.2 拒绝检测

在外层循环中，对用户输入进行关键词匹配：

```python
rejection_keywords = ["不要", "不喜欢", "不好", "换一个",
                      "拒绝", "不行", "太贵", "不好玩", "去过"]
is_rejection = any(kw in user_input for kw in rejection_keywords)
```

### 4.3 反思 Prompt 设计

当 `rejection_count >= 3` 时，构建一个**反思 Prompt** 单独调用 LLM：

```
【系统反思指令 — 请务必执行】

用户已连续拒绝了 3 次推荐。

过去的拒绝原因:
1. 不要故宫，人太多
2. 不喜欢爬山
3. 这个景点太贵了

请执行以下反思步骤:
1. 分析：用户为什么一直在拒绝？
2. 总结：从拒绝原因中推断用户真实偏好
3. 调整策略：完全换一个方向，不要微调
4. 记录洞察：调用 update_memory 记录推断出的偏好
5. 直接询问用户到底想要什么（给出 2-3 个选项）
```

### 4.4 为什么单独调用 LLM 而不是注入 ReAct 循环？

反思需要一个**更高层次的、跳出当前推理链的思考**。如果把反思指令直接塞进 ReAct 循环，LLM 容易在当前的推荐路径上微调（"那我换个便宜点的"），而不是真正反思策略方向（"用户可能根本不需要景点推荐，而是需要路线规划"）。

---

## 五、文件修改记录（对比原版）

| 位置 | 修改类型 | 说明 |
|------|---------|------|
| `AGENT_SYSTEM_PROMPT` | **追加** | 新增 2 个工具说明、售罄处理规则、偏好记忆说明 |
| 第 75 行后 | **追加** | `check_ticket_availability()` 函数 |
| 第 90 行后 | **追加** | `PreferenceMemory` 类 + 全局 `memory` 实例 |
| `available_tools` | **追加** | 注册 `check_ticket_availability` 和 `memory.update` |
| 配置段 | **改良** | 加入 `load_dotenv()` 从 `.env` 读取密钥 |
| 原 for 循环后 | **追加** | `run_react_cycle()` 函数（内层 ReAct 封装） |
| 文件末尾 | **追加** | `main()` 交互式主循环 + `if __name__` 守卫 |

**未删除/改动部分**：`get_weather`、`get_attraction`、`OpenAICompatibleClient`、原系统提示词结构、原 for 循环演示逻辑。

---

## 六、运行指南

### 安装依赖

```bash
pip install openai tavily-python requests python-dotenv
```

### 配置密钥

`.env` 文件已存在（位于 `chapter1/.env`）：

```
TAVILY_API_KEY=tvly-dev-xxxxx
API_KEY=sk-eabe3414750b44a499c5129c2d4a2660
BASE_URL=https://api.deepseek.com/v1
MODEL_ID=deepseek-v4-flash
```

### 运行

```bash
cd chapter1
python FirstAgentTest.py
```

程序会先执行一次原版的单次演示（查询北京天气 → 推荐景点），然后进入交互式模式。

### 测试验证

运行独立的模块测试：

```bash
python test_v2_features.py
```

---

## 七、扩展思考

### 持久化记忆

当前记忆存在于内存中，程序重启后丢失。可以改为：

```python
import json
class PersistentMemory(PreferenceMemory):
    def save(self, path="memory.json"):
        with open(path, "w") as f:
            json.dump({
                "likes": list(self.likes),
                "dislikes": list(self.dislikes),
                "budget": self.budget,
                "travel_style": self.travel_style
            }, f)

    def load(self, path="memory.json"):
        with open(path) as f:
            data = json.load(f)
            self.likes = set(data["likes"])
            # ...
```

### 门票检查真实化

当前 `SOLD_OUT_ATTRACTIONS` 是硬编码的模拟。真实场景可以接入景区票务 API 或爬取实时数据。

### 更智能的拒绝检测

当前基于关键词匹配，有误判风险（"我不去**不行**"会被判为拒绝）。可以改用 LLM 的情感分析来判断。

---

## 附：心智模型速查

```
┌──────────────────────────────┐
│    你想让 LLM 做什么？         │
├──────────────────────────────┤
│ 记住用户偏好                  │
│   → 加一个记忆存储类           │
│   → 通过 update_memory 工具   │
│   → 在 System Prompt 注入     │
├──────────────────────────────┤
│ 门票售罄后自动换推荐           │
│   → 加一个门票检查工具          │
│   → ReAct 天然支持自动重试      │
│   → 不需要额外分支代码          │
├──────────────────────────────┤
│ 连续被拒后反思策略             │
│   → 外层循环计数               │
│   → 达到阈值构建反思 Prompt    │
│   → 单独调用 LLM（跳出循环）    │
└──────────────────────────────┘
```
