# 课堂视频智能分析工具

基于火花思维教学评价体系的课堂视频质量分析工具。

## 核心流程

视频 → FFmpeg音频提取 → 腾讯云ASR → LLM事件检测 → 视觉预观察(8维度) → 互动链重构 → LLM质量评估 → 报告生成

## 技术栈

- Python 3.13 + FastAPI
- React + MUI + Tailwind CSS
- DeepSeek (文本模型) + 豆包视觉 (视觉模型)
- 腾讯云 ASR + FFmpeg

## 本地开发

```bash
# 安装依赖
pip install -e .

# 构建前端
cd web && npm install && npm run build

# 启动服务
uvicorn classroom_analyzer.server.app:app --host 0.0.0.0 --port 8001
```

## 云端部署 (Render)

1. Fork 本仓库到你的 GitHub
2. 在 [Render](https://render.com) 创建新的 Web Service
3. 连接你的 GitHub 仓库
4. Render 会自动检测 `render.yaml` 配置
5. 在环境变量中设置 `API_KEYS_JSON`（包含所有API密钥的JSON字符串）

### 环境变量

- `API_KEYS_JSON`: 完整的API密钥配置JSON（见 config/api_keys.json 格式）
- `PORT`: 服务端口，默认 8001

## 评分体系

4类目 × 10维度 = 100分制（75分合格线）

- 教学内容(30): 知识传授/熟练程度/重点难点
- 教学方法(20): 教学方式方法/教学逻辑
- 教学规范(35): 组织教学/仪表教态*/语言表达及板书设计*/关注公平
- 课堂效果(15): 课堂效果及整体印象

(*视觉维度，由视觉模型直接评分)

等级：优[85-100] 良[75-85) 待改进[50-75) 不合格[0-50)
