"""快速验证 Qwen-VL API 连通性 — 1张图片"""
import base64
import json
from openai import OpenAI

API_KEY = "sk-873d32e2b603471c9fde5326e064b1e1"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-vl-max"

# 找一张测试图片
import os
from pathlib import Path
kf_dir = Path("output/ks_video_20260606/keyframes")
imgs = sorted(kf_dir.glob("*.jpg"))
if not imgs:
    print("ERROR: no keyframes found!")
    exit(1)
test_img = imgs[0]
print(f"测试图片: {test_img} ({test_img.stat().st_size} bytes)")

# base64编码
with open(test_img, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")
print(f"base64长度: {len(b64)} chars")

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=60.0,
)

messages = [
    {"role": "system", "content": "你是一个图片分析助手。请用中文回答。"},
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "请描述这张图片的内容，简要说明你看到了什么。"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            }
        ]
    }
]

print("发送请求到 Qwen-VL...")
try:
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.1,
        max_tokens=1024,
    )
    content = response.choices[0].message.content
    print(f"✅ API调用成功！")
    print(f"Token用量: {response.usage}")
    print(f"响应: {content[:500]}")
except Exception as e:
    print(f"❌ API调用失败: {e}")
