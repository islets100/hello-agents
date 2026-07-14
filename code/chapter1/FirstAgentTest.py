AGENT_SYSTEM_PROMPT = """
你是一个智能旅行助手。你的任务是分析用户的请求，并使用可用工具一步步地解决问题。

# 可用工具:
- `get_weather(city: str)`: 查询指定城市的实时天气。
- `get_attraction(city: str, weather: str)`: 根据城市和天气搜索推荐的旅游景点。
- `check_ticket_availability(attraction: str)`: 检查指定景点门票是否可购买。
- `update_memory(key: str, value: str)`: 记录用户的偏好信息。key可选: like/dislike/budget/travel_style。

# 门票售罄处理规则:
- 如果 Observation 显示门票已售罄，请自动推荐替代景点。
- 结合用户的出行偏好（历史文化/自然风光/休闲购物），推荐相似类型的备选方案。
- 不要简单地重复之前的推荐。

# 偏好记忆说明:
- 系统会在每次请求前注入用户的偏好记忆作为上下文。
- 你在推理时应参考这些记忆，避免推荐用户不感兴趣的内容。
- 当用户表达了明确的喜好或厌恶时，及时调用 update_memory 记录下来。

# 输出格式要求:
你的每次回复必须严格遵循以下格式，包含一对Thought和Action：

Thought: [你的思考过程和下一步计划]
Action: [你要执行的具体行动]

Action的格式必须是以下之一：
1. 调用工具：function_name(arg_name="arg_value")
2. 结束任务：Finish[最终答案]

# 重要提示:
- 每次只输出一对Thought-Action
- Action必须在同一行，不要换行
- 当收集到足够信息可以回答用户问题时，必须使用 Action: Finish[最终答案] 格式结束

请开始吧！
"""


import requests

def get_weather(city: str) -> str:
    """
    通过调用 wttr.in API 查询真实的天气信息。
    """
    # API端点，我们请求JSON格式的数据
    url = f"https://wttr.in/{city}?format=j1"
    
    try:
        # 发起网络请求
        response = requests.get(url)
        # 检查响应状态码是否为200 (成功)
        response.raise_for_status() 
        # 解析返回的JSON数据
        data = response.json()
        
        # 提取当前天气状况
        current_condition = data['current_condition'][0]
        weather_desc = current_condition['weatherDesc'][0]['value']
        temp_c = current_condition['temp_C']
        
        # 格式化成自然语言返回
        return f"{city}当前天气：{weather_desc}，气温{temp_c}摄氏度"
        
    except requests.exceptions.RequestException as e:
        # 处理网络错误
        return f"错误：查询天气时遇到网络问题 - {e}"
    except (KeyError, IndexError) as e:
        # 处理数据解析错误
        return f"错误：解析天气数据失败，可能是城市名称无效 - {e}"



import os
from tavily import TavilyClient

def get_attraction(city: str, weather: str) -> str:
    """
    根据城市和天气，使用Tavily Search API搜索并返回优化后的景点推荐。
    """

    # 从环境变量或主程序配置中获取API密钥
    api_key = os.environ.get("TAVILY_API_KEY") # 推荐方式
    # 或者，我们可以在主循环中传入，如此处代码所示

    if not api_key:
        return "错误：未配置TAVILY_API_KEY。"

    # 2. 初始化Tavily客户端
    tavily = TavilyClient(api_key=api_key)
    
    # 3. 构造一个精确的查询
    query = f"'{city}' 在'{weather}'天气下最值得去的旅游景点推荐及理由"
    
    try:
        # 4. 调用API，include_answer=True会返回一个综合性的回答
        response = tavily.search(query=query, search_depth="basic", include_answer=True)
        
        # 5. Tavily返回的结果已经非常干净，可以直接使用
        # response['answer'] 是一个基于所有搜索结果的总结性回答
        if response.get("answer"):
            return response["answer"]
        
        # 如果没有综合性回答，则格式化原始结果
        formatted_results = []
        for result in response.get("results", []):
            formatted_results.append(f"- {result['title']}: {result['content']}")
        
        if not formatted_results:
             return "抱歉，没有找到相关的旅游景点推荐。"

        return "根据搜索，为您找到以下信息：\n" + "\n".join(formatted_results)

    except Exception as e:
        return f"错误：执行Tavily搜索时出现问题 - {e}"


# ========== 新增功能：门票检查（模拟） ==========

# 模拟已售罄的热门景点集合
SOLD_OUT_ATTRACTIONS = {"故宫博物院", "上海迪士尼乐园", "北京环球影城", "秦始皇兵马俑"}

def check_ticket_availability(attraction: str) -> str:
    """
    检查指定景点门票是否可购买。
    模拟实现：预设部分热门景点为已售罄状态。
    """
    if attraction in SOLD_OUT_ATTRACTIONS:
        return f"很抱歉，{attraction}的门票已售罄。建议您考虑其他相似景点。"
    return f"好消息！{attraction}的门票可以购买。"


# ========== 新增功能：偏好记忆系统 ==========

class PreferenceMemory:
    """
    记录用户的偏好信息，每次请求前注入到 System Prompt。
    支持：喜欢的类型、不喜欢的类型、预算范围、出行风格。
    """
    def __init__(self):
        self.likes = set()
        self.dislikes = set()
        self.budget = None
        self.travel_style = None

    def update(self, key: str, value: str) -> str:
        """更新偏好记忆，由 LLM 在推理过程中主动调用。"""
        key = key.lower().strip()
        value = value.strip()
        if key == "like":
            self.likes.add(value)
            return f"✅ 已记录偏好：喜欢 {value}"
        elif key == "dislike":
            self.dislikes.add(value)
            return f"✅ 已记录偏好：不喜欢 {value}"
        elif key == "budget":
            self.budget = value
            return f"✅ 已记录预算范围：{value}"
        elif key == "travel_style":
            self.travel_style = value
            return f"✅ 已记录出行风格：{value}"
        return f"❌ 未知的记忆类型: {key}，可选: like/dislike/budget/travel_style"

    def to_context(self) -> str:
        """生成注入到 System Prompt 的偏好上下文。"""
        parts = []
        if self.likes:
            parts.append(f"- 👍 用户喜欢的类型: {', '.join(self.likes)}")
        if self.dislikes:
            parts.append(f"- 👎 用户不喜欢的类型: {', '.join(self.dislikes)}")
        if self.budget:
            parts.append(f"- 💰 预算范围: {self.budget}")
        if self.travel_style:
            parts.append(f"- 🎯 出行风格: {self.travel_style}")
        if not parts:
            return ""
        return "\n\n---\n📋 **用户偏好记忆（请参考）**\n" + "\n".join(parts) + "\n---"


# 全局记忆实例（供工具函数和主循环共享）
memory = PreferenceMemory()


# 将所有工具函数放入一个字典，方便后续调用
available_tools = {
    "get_weather": get_weather,
    "get_attraction": get_attraction,
    "check_ticket_availability": check_ticket_availability,
    "update_memory": memory.update,
}

from openai import OpenAI

class OpenAICompatibleClient:
    """
    一个用于调用任何兼容OpenAI接口的LLM服务的客户端。
    """
    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, prompt: str, system_prompt: str) -> str:
        """调用LLM API来生成回应。"""
        print("正在调用大语言模型...")
        try:
            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt}
            ]
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False
            )
            answer = response.choices[0].message.content
            print("大语言模型响应成功。")
            return answer
        except Exception as e:
            print(f"调用LLM API时发生错误: {e}")
            return "错误：调用语言模型服务时出错。"

from dotenv import load_dotenv
import re

# --- 1. 配置LLM客户端 ---
# 优先从 .env 文件加载，未配置时使用占位符
load_dotenv()
API_KEY = os.getenv("API_KEY") or "YOUR_API_KEY"
BASE_URL = os.getenv("BASE_URL") or "YOUR_BASE_URL"
MODEL_ID = os.getenv("MODEL_ID") or "YOUR_MODEL_ID"
TAVILY_KEY = os.getenv("TAVILY_API_KEY") or "YOUR_TAVILY_API_KEY"
os.environ['TAVILY_API_KEY'] = TAVILY_KEY

llm = OpenAICompatibleClient(
    model=MODEL_ID,
    api_key=API_KEY,
    base_url=BASE_URL
)

# --- 2. 初始化 ---
user_prompt = "你好，请帮我查询一下今天北京的天气，然后根据天气推荐一个合适的旅游景点。"
prompt_history = [f"用户请求: {user_prompt}"]

print(f"用户输入: {user_prompt}\n" + "="*40)

# --- 3. 运行主循环 ---
for i in range(5): # 设置最大循环次数
    print(f"--- 循环 {i+1} ---\n")
    
    # 3.1. 构建Prompt
    full_prompt = "\n".join(prompt_history)
    
    # 3.2. 调用LLM进行思考
    llm_output = llm.generate(full_prompt, system_prompt=AGENT_SYSTEM_PROMPT)
    # 模型可能会输出多余的Thought-Action，需要截断
    match = re.search(r'(Thought:.*?Action:.*?)(?=\n\s*(?:Thought:|Action:|Observation:)|\Z)', llm_output, re.DOTALL)
    if match:
        truncated = match.group(1).strip()
        if truncated != llm_output.strip():
            llm_output = truncated
            print("已截断多余的 Thought-Action 对")
    print(f"模型输出:\n{llm_output}\n")
    prompt_history.append(llm_output)
    
    # 3.3. 解析并执行行动
    action_match = re.search(r"Action: (.*)", llm_output, re.DOTALL)
    if not action_match:
        observation = "错误: 未能解析到 Action 字段。请确保你的回复严格遵循 'Thought: ... Action: ...' 的格式。"
        observation_str = f"Observation: {observation}"
        print(f"{observation_str}\n" + "="*40)
        prompt_history.append(observation_str)
        continue
    action_str = action_match.group(1).strip()

    if action_str.startswith("Finish"):
        final_answer = re.match(r"Finish\[(.*)\]", action_str).group(1)
        print(f"任务完成，最终答案: {final_answer}")
        break
    
    tool_name = re.search(r"(\w+)\(", action_str).group(1)
    args_str = re.search(r"\((.*)\)", action_str).group(1)
    kwargs = dict(re.findall(r'(\w+)="([^"]*)"', args_str))

    if tool_name in available_tools:
        observation = available_tools[tool_name](**kwargs)
    else:
        observation = f"错误：未定义的工具 '{tool_name}'"

    # 3.4. 记录观察结果
    observation_str = f"Observation: {observation}"
    print(f"{observation_str}\n" + "="*40)
    prompt_history.append(observation_str)


# ====================================================================
# 新增：交互式对话模式 — 记忆 + 门票售罄备选 + 3次拒绝反思
# ====================================================================

def run_react_cycle(user_input: str, llm_client, max_steps: int = 5) -> tuple[list, bool]:
    """
    执行一次 ReAct 推理循环（内层）。
    参数:
        user_input: 用户本轮输入
        llm_client: LLM 客户端
        max_steps: 最大推理步数
    返回:
        (本轮完整的对话历史列表, 是否成功完成)
        - 成功完成: 以 Finish[...] 正常结束
        - 未完成: 达到 max_steps 上限仍未 Finish
    """
    prompt_history = [f"用户请求: {user_input}"]

    for step in range(max_steps):
        print(f"\n--- 步骤 {step+1} ---")

        # 构建完整 Prompt = 对话历史 + 偏好记忆上下文
        conversation = "\n".join(prompt_history)
        memory_context = memory.to_context()
        full_prompt = conversation + memory_context

        # 调用 LLM
        llm_output = llm_client.generate(full_prompt, system_prompt=AGENT_SYSTEM_PROMPT)

        # 截断多余的 Thought-Action 对
        match = re.search(
            r'(Thought:.*?Action:.*?)(?=\n\s*(?:Thought:|Action:|Observation:)|\Z)',
            llm_output, re.DOTALL
        )
        if match:
            truncated = match.group(1).strip()
            if truncated != llm_output.strip():
                llm_output = truncated
                print("(已截断多余的 Thought-Action 对)")

        print(f"模型输出:\n{llm_output}\n")
        prompt_history.append(llm_output)

        # 解析 Action
        action_match = re.search(r"Action: (.*)", llm_output, re.DOTALL)
        if not action_match:
            obs = "错误: 未能解析到 Action 字段。"
            obs_str = f"Observation: {obs}"
            print(obs_str)
            prompt_history.append(obs_str)
            continue

        action_str = action_match.group(1).strip()

        # Finish → 结束本轮推理
        if action_str.startswith("Finish"):
            final_match = re.match(r"Finish\[(.*)\]", action_str)
            if final_match:
                final_answer = final_match.group(1)
                print(f"\n✅ 任务完成！\n{final_answer}")
                prompt_history.append(f"\n🤖 最终回答: {final_answer}")
            else:
                print("\n✅ 任务完成！")
                prompt_history.append("\n🤖 任务完成。")
            return prompt_history, True

        # 解析工具调用：get_weather(city="北京")
        tool_match = re.search(r"(\w+)\(", action_str)
        if not tool_match:
            obs = "错误: 无法解析工具调用。"
            prompt_history.append(f"Observation: {obs}")
            continue

        tool_name = tool_match.group(1)
        args_match = re.search(r"\((.*)\)", action_str)
        args_str = args_match.group(1) if args_match else ""
        kwargs = dict(re.findall(r'(\w+)="([^"]*)"', args_str))

        # 执行工具
        if tool_name in available_tools:
            print(f"🔧 执行工具: {tool_name}({kwargs})")
            try:
                observation = available_tools[tool_name](**kwargs)
            except Exception as e:
                observation = f"错误：执行 {tool_name} 时发生异常 - {e}"
        else:
            observation = f"错误：未定义的工具 '{tool_name}'"

        obs_str = f"Observation: {observation}"
        print(f"{obs_str}\n" + "=" * 40)
        prompt_history.append(obs_str)

    # 达到最大步数仍未 Finish
    print("\n⚠️ 已达到最大推理步数，本轮结束。")
    return prompt_history, False


def main():
    """
    交互式主循环（外层对话层）。
    在原有 ReAct 单次执行的基础上，增加:
      1. 多轮对话能力（用户连续输入）
      2. 偏好记忆（存入 PreferenceMemory）
      3. 拒绝跟踪 → 3次触发反思
    """
    # 检查是否配置了 API 密钥
    if API_KEY == "YOUR_API_KEY":
        print("⚠️  检测到 API 密钥仍为占位符，请先配置 .env 文件或直接修改变量。")
        print("继续使用交互模式可能导致调用失败。\n")

    llm = OpenAICompatibleClient(
        model=MODEL_ID,
        api_key=API_KEY,
        base_url=BASE_URL
    )

    # ---------- 拒绝跟踪 ----------
    rejection_count = 0
    rejection_reasons = []

    print("=" * 56)
    print("  🌍  智能旅行助手 v2 — 记忆 & 反思")
    print("=" * 56)
    print("支持功能:")
    print("  ✅ 偏好记忆 — 自动学习你的喜好")
    print("  ✅ 门票检查 — 售罄后自动推荐备选")
    print("  ✅ 3次拒绝后反思 — 调整推荐策略")
    print("  ✅ 任务完成后询问是否继续，无需记命令")
    print("  " + "─" * 50)
    print("随时输入 'exit' / 'quit' 退出对话。\n")

    first_turn = True

    while True:
        # ---------- 获取用户输入 ----------
        if first_turn:
            try:
                user_input = input("\n👤 请输入您的旅行需求: ")
            except (EOFError, KeyboardInterrupt):
                print("\n👋 再见！")
                break
            first_turn = False
        else:
            try:
                user_input = input("\n👤 请输入反馈或新的需求: ")
            except (EOFError, KeyboardInterrupt):
                print("\n👋 再见！")
                break

        if user_input.lower() in ('exit', 'quit', 'q'):
            print("👋 再见！")
            break

        if not user_input.strip():
            continue

        # ---------- 检测用户是否拒绝 ----------
        rejection_keywords = ["不要", "不喜欢", "不好", "换一个", "拒绝", "不行", "太贵", "不好玩", "去过"]
        is_rejection = any(kw in user_input for kw in rejection_keywords)

        if is_rejection:
            rejection_count += 1
            rejection_reasons.append(user_input)

            # 从拒绝反馈中提取偏好，记录到记忆
            for word in ["喜欢", "想要", "想去"]:
                if word in user_input:
                    memory.update("like", "用户表达了新的兴趣方向")
                    break
            for word in ["太贵", "太远", "不感兴趣", "不好玩", "去过"]:
                if word in user_input:
                    memory.update("dislike", word)
                    break

            print(f"\n📊 拒绝计数: {rejection_count}/3")
            print(f"📝 拒绝原因: {user_input}")

        # ---------- 🚨 连续3次拒绝 → 触发反思 ----------
        if rejection_count >= 3:
            print("\n" + "⚠️" * 20)
            print("  用户已连续拒绝 3 次推荐，正在触发自我反思...")
            print("⚠️" * 20)

            # 构建反思 Prompt
            reflection_prompt = f"""
【系统反思指令 — 请务必执行】

用户已连续拒绝了 {rejection_count} 次推荐。

### 过去的拒绝原因:
"""
            for i, reason in enumerate(rejection_reasons, 1):
                reflection_prompt += f"{i}. {reason}\n"

            reflection_prompt += """

### 请执行以下反思步骤:
1. 分析：用户为什么一直在拒绝？我的推荐方向出了什么问题？
2. 总结：从拒绝原因中可以推断出用户的哪些真实偏好？
3. 调整策略：完全换一个方向思考，不要微调当前方案
4. 记录洞察：调用 update_memory 记录你推断出的用户偏好
5. 然后直接询问用户：您到底想要什么样的推荐？（给出 2-3 个具体选项供选择）

现在请开始反思，输出 Thought 和 Action。
"""

            # 单独调用 LLM 进行反思
            print("\n🤔 正在调用 LLM 进行策略反思...")
            reflection_result = llm.generate(reflection_prompt, AGENT_SYSTEM_PROMPT + memory.to_context())
            print(f"\n💡 反思输出:\n{reflection_result}\n")

            # 将反思结果注入后续对话
            # 重置计数器
            rejection_count = 0
            rejection_reasons.clear()

        # ---------- 执行 ReAct 推理 ----------
        print("\n" + "─" * 50)
        print("🧠 开始推理...")
        print("─" * 50)
        _, task_completed = run_react_cycle(user_input, llm)

        # ---------- 展示当前记忆状态 ----------
        print("\n" + "─" * 50)
        memory_state = memory.to_context()
        if memory_state:
            print("💾 当前偏好记忆:\n" + memory_state)
        else:
            print("💾 当前尚无偏好记录")
        print("─" * 50)

        # ---------- 任务完成后询问是否继续 ----------
        if task_completed:
            try:
                cont = input("\n🔁 是否继续提问？(y/n，默认 y): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 再见！")
                break
            if cont in ('n', 'no', '不', '否'):
                print("👋 再见！")
                break
            # 用户选择继续，重置 first_turn 提示风格
            print()  # 空行保持视觉分隔


# ====================================================================
# 入口：原有逻辑 + 交互式模式并存在同一个文件中
# ====================================================================
# 原有主逻辑（上面的 for 循环）依然会执行一次演示。
# 然后交互式模式启动。
#
# 如果想直接进入交互模式，可以将下面这行取消注释，
# 并将原有的 for 循环部分注释掉。
# ====================================================================

if __name__ == "__main__":
    main()
