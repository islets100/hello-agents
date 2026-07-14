import re
import random


# =============================================================================
# 规则库（原版 6 条 + 新增 5 条）
# 新增规则涵盖：工作、学习、爱好、情绪、未来计划
# =============================================================================
rules = {
    # ---------- 原版 6 条 ----------
    r'I need (.*)': [
        "Why do you need {0}?",
        "Would it really help you to get {0}?",
        "Are you sure you need {0}?"
    ],
    r'Why don\'t you (.*)\?': [
        "Do you really think I don't {0}?",
        "Perhaps eventually I will {0}.",
        "Do you really want me to {0}?"
    ],
    r'Why can\'t I (.*)\?': [
        "Do you think you should be able to {0}?",
        "If you could {0}, what would you do?",
        "I don't know -- why can't you {0}?"
    ],
    r'I am (.*)': [
        "Did you come to me because you are {0}?",
        "How long have you been {0}?",
        "How do you feel about being {0}?"
    ],
    r'.* mother .*': [
        "Tell me more about your mother.",
        "What was your relationship with your mother like?",
        "How do you feel about your mother?"
    ],
    r'.* father .*': [
        "Tell me more about your father.",
        "How did your father make you feel?",
        "What has your father taught you?"
    ],

    # ---------- 新增 1：谈论工作 ----------
    r'.*(?:work|job|career|colleague|boss|工作|上班).*': [
        "How do you feel about your work?",
        "What would you change about your job if you could?",
        "Has your work been stressful lately?",
        "Tell me more about your relationship with your colleagues."
    ],

    # ---------- 新增 2：谈论学习 ----------
    r'.*(?:study|learn|school|exam|university|college|学习|考试).*': [
        "What subjects interest you the most?",
        "How do you feel about your studies?",
        "What would you like to learn that you haven't yet?",
        "Does studying bring you joy or pressure?"
    ],

    # ---------- 新增 3：谈论爱好 ----------
    r'.*(?:hobby|like to|enjoy|love to|兴趣|喜欢|爱好).*': [
        "What draws you to that hobby?",
        "How much time do you spend on things you enjoy?",
        "Does that activity help you relax?",
        "Have you always enjoyed {0}?"
    ],

    # ---------- 新增 4：表达情绪 ----------
    r'.*(?:happy|sad|angry|upset|excited|anxious|开心|难过|生气).*': [
        "How long have you been feeling this way?",
        "What do you think triggered that emotion?",
        "Can you describe what that feels like for you?",
        "Is this a feeling that comes to you often?"
    ],

    # ---------- 新增 5：谈论未来 ----------
    r'.*(?:future|plan|goal|dream|tomorrow|将来|计划|目标|梦想).*': [
        "What do you hope your future will look like?",
        "What steps are you taking toward that goal?",
        "Have your plans changed over time?",
        "What would achieving that dream mean to you?"
    ],

    # ---------- 兜底规则 ----------
    r'.*': [
        "Please tell me more.",
        "Let's change focus a bit... Tell me about your family.",
        "Can you elaborate on that?",
        "I see. How does that make you feel?",
        "What do you think about that?"
    ]
}


# =============================================================================
# 代词转换（与原版保持一致）
# =============================================================================
pronoun_swap = {
    "i": "you", "you": "i", "me": "you", "my": "your",
    "am": "are", "are": "am", "was": "were", "i'd": "you would",
    "i've": "you have", "i'll": "you will", "yours": "mine",
    "mine": "yours"
}


def swap_pronouns(phrase):
    words = phrase.lower().split()
    swapped_words = [pronoun_swap.get(word, word) for word in words]
    return " ".join(swapped_words)


# =============================================================================
# ★ 上下文记忆系统
# =============================================================================
class ContextMemory:
    """
    从用户对话中提取姓名、年龄、职业等关键信息，并在后续对话中引用。
    """
    def __init__(self):
        self.name = None        # 用户姓名
        self.age = None         # 用户年龄
        self.occupation = None  # 用户职业
        self.mentioned_topics = []  # 最近提及的话题列表

    # ----- 信息提取 -----
    def extract_and_store(self, user_input: str):
        """从用户输入中提取关键信息并存储"""
        # 提取姓名（中文 / 英文）
        name_patterns = [
            r'我叫\s*([一-龥]{2,4})',
            r'我是\s*([一-龥]{2,4})',
            r'my name is (\w+)',
            r"i'm (\w+)",
            r'call me (\w+)',
        ]
        for pat in name_patterns:
            m = re.search(pat, user_input, re.IGNORECASE)
            if m:
                new_name = m.group(1).strip()
                if self.name != new_name:
                    self.name = new_name
                    return True  # 新信息已记录

        # 提取年龄
        age_match = re.search(r'(\d{1,3})\s*(?:岁|years?\s*old)', user_input, re.IGNORECASE)
        if age_match:
            new_age = int(age_match.group(1))
            if 1 <= new_age <= 120 and self.age != new_age:
                self.age = new_age
                return True

        # 提取职业
        occ_patterns = [
            r'我是[一]?[个名]?\s*([一-龥]{2,6})\s*(?:，|。)',
            r'(?:i am|i\'m)\s+a?\s*(\w[\w\s]{1,20})',
            r'(?:i work as|my job is)\s+a?\s*(\w[\w\s]{1,20})',
        ]
        for pat in occ_patterns:
            m = re.search(pat, user_input, re.IGNORECASE)
            if m:
                new_occ = m.group(1).strip()
                if self.occupation != new_occ:
                    self.occupation = new_occ
                    return True

        # 记录提及话题（防重复，最近优先）
        for kw, label in [
            ("工作|上班|work|job", "工作"),
            ("学习|考试|study|exam|school", "学习"),
            ("喜欢|爱好|hobby|interest", "爱好"),
            ("难过|开心|生气|happy|sad|angry", "情绪"),
            ("家庭|家人|mother|father|父母", "家庭"),
        ]:
            if re.search(kw, user_input, re.IGNORECASE) and label not in self.mentioned_topics:
                self.mentioned_topics.insert(0, label)
                if len(self.mentioned_topics) > 3:
                    self.mentioned_topics.pop()

        return False  # 没有新信息

    # ----- 记忆引用 -----
    def inject_memory(self, response: str) -> str:
        """在生成的回复前，按概率追加记忆引用的前缀"""
        # 约 25% 概率触发记忆引用
        if random.random() > 0.25:
            return response

        prefixes = []
        if self.name and random.random() < 0.6:
            prefixes.append(f"{self.name}")
        if self.age and random.random() < 0.3:
            prefixes.append(f"作为一个{self.age}岁的人")
        if self.occupation and random.random() < 0.4:
            prefixes.append(f"身为{self.occupation}")

        if prefixes:
            prefix = "，".join(prefixes)
            connectors = [
                f"{prefix}，你觉得",
                f"{prefix}，",
                f"说到这个，{prefix}，"
            ]
            # 如果已有引用，替换原回复的开头；否则前置
            connector = random.choice(connectors)
            if connector.endswith("，"):
                # 将记忆信息自然地拼到回复前面
                response = connector + " " + response[0].lower() + response[1:]
            else:
                response = connector + " " + response

        return response


# 全局上下文记忆实例
memory = ContextMemory()


# =============================================================================
# 响应生成（加入记忆提取与注入）
# =============================================================================
def respond(user_input):
    """
    根据规则库生成响应，同时提取并引用上下文记忆。
    """
    # ★ Step 1：从用户输入中提取关键信息
    new_info_recorded = memory.extract_and_store(user_input)

    # ★ Step 2：规则匹配
    matched_response = None
    for pattern, responses in rules.items():
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            captured_group = match.group(1) if match.groups() else ''
            swapped_group = swap_pronouns(captured_group)
            matched_response = random.choice(responses).format(swapped_group)
            break

    if matched_response is None:
        matched_response = random.choice(rules[r'.*'])

    # ★ Step 3：记忆引用（仅在新信息被记录时提高触发概率）
    # 实际中始终注入，内部有随机概率控制
    response = memory.inject_memory(matched_response)

    return response


# =============================================================================
# 主聊天循环
# =============================================================================
if __name__ == '__main__':
    print("=" * 50)
    print("  ELIZA Enhanced — 扩展规则 + 上下文记忆")
    print("  规则数: {}  |  支持: 工作/学习/爱好/情绪/未来" .format(len(rules)))
    print("=" * 50)
    print("Therapist: 你好！今天想聊些什么？")
    print("  (输入 'quit' / 'exit' / 'bye' 退出)")
    print("  (输入 'memory' 查看当前记忆的内容)\n")

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nTherapist: Goodbye. It was nice talking to you.")
            break

        if user_input.lower() in ["quit", "exit", "bye"]:
            print("Therapist: Goodbye. It was nice talking to you.")
            break

        if user_input.lower() == "memory":
            print(f"[Memory] 姓名: {memory.name or '(未记录)'}")
            print(f"[Memory] 年龄: {memory.age or '(未记录)'}")
            print(f"[Memory] 职业: {memory.occupation or '(未记录)'}")
            print(f"[Memory] 近期话题: {memory.mentioned_topics or '(无)'}")
            continue

        if not user_input.strip():
            continue

        response = respond(user_input)
        print(f"Therapist: {response}")
