# AI 学术写作助手

面向学术写作与毕业论文处理的本地 Web 工具，基于 `FastAPI + React + PyInstaller` 构建。项目提供 AI 论文润色、原创性增强、降 AIGC 辅助、后台配置和 Word 结果导出能力，适合用于毕业设计说明书、课程论文和学术文本优化场景。

## 功能说明

### 1. 学术文本优化

- 双阶段处理：先进行语言润色，再进行学术表达增强
- 支持自定义系统提示词与分阶段模型配置
- 自动分段处理正文，跳过过短段落
- 支持按卡密控制使用次数，适合本地部署或小范围分发

### 2. 论文 Word 处理与导出

- 支持从 `.docx` 文档中提取正文和目录结构
- 支持论文正文润色、表达增强和降 AIGC 辅助处理
- 支持查看修改记录并导出处理后的 Word 文档

### 3. 系统管理与运行配置

- 提供管理员后台，可管理卡密、使用记录和系统配置
- 可在线修改模型、Base URL、请求间隔、并发数量等配置
- 支持模型健康检查
- 支持打包为单文件 exe，本地一键启动

## 界面预览

<img width="2080" height="1361" alt="图片" src="https://github.com/user-attachments/assets/c11abdc9-4bc4-4d61-bea0-13071dba01cd" />

<img width="2103" height="1337" alt="图片" src="https://github.com/user-attachments/assets/523da9c2-899d-4739-932e-84af881a1dfd" />

## 技术架构

- 后端：`FastAPI`、`SQLAlchemy`、`Pydantic`、`Redis`
- 前端：`React`、`Vite`、`Tailwind CSS`
- AI 调用：兼容 OpenAI API 格式接口
- Word 处理：`python-docx`
- 打包：`PyInstaller`

## 源码结构

```text
BypassAIGC/
├── docs/
│   └── plans/                         # 设计记录
├── package/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── models/               # 数据模型
│   │   │   ├── routes/               # 后端路由
│   │   │   ├── services/             # AI 调用、正文提取、并发控制等服务
│   │   │   ├── config.py             # 配置读取
│   │   │   ├── database.py           # 数据库初始化
│   │   │   └── main.py               # 后端 API 入口
│   │   └── requirements.txt          # 后端依赖
│   ├── frontend/
│   │   ├── src/
│   │   │   ├── components/           # 公共组件
│   │   │   └── pages/                # 页面组件
│   │   ├── package.json
│   │   └── vite.config.js
│   ├── static/                       # 前端构建产物
│   ├── dist/                         # 打包输出目录
│   ├── app.spec                      # PyInstaller 配置
│   ├── build.ps1                     # Windows 打包脚本
│   ├── main.py                       # 整体启动入口
│   └── README.md                     # 打包说明
├── .gitignore
└── README.md
```

## 本地部署

### 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 优先 |
| Python | 3.9 及以上 |
| Node.js | 18 及以上 |
| npm | 随 Node.js 安装 |
| PowerShell | 建议 7.x |
| Microsoft Word | 需要使用 Word 写回时必须安装 |

### 克隆项目

```powershell
git clone https://github.com/xyy54323/BypassAIGC_docx.git
cd BypassAIGC_docx
```

### 安装后端依赖

```powershell
cd package
python -m venv venv
.\venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 安装前端依赖并构建

```powershell
cd frontend
npm install
npm run build
cd ..
```

首次本地运行前，需要把前端构建产物复制到 `package/static`：

```powershell
if (Test-Path .\static) { Remove-Item -Recurse -Force .\static }
Copy-Item -Recurse .\frontend\dist .\static
```

### 配置 `.env`

源码模式推荐在 `package/.env` 下创建配置文件。最小可用配置示例：

```properties
SERVER_HOST=0.0.0.0
SERVER_PORT=9800

OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

POLISH_MODEL=gpt-5
POLISH_API_KEY=your-api-key
POLISH_BASE_URL=https://api.openai.com/v1

ENHANCE_MODEL=gpt-5
ENHANCE_API_KEY=your-api-key
ENHANCE_BASE_URL=https://api.openai.com/v1

SECRET_KEY=please-change-this-to-a-random-string
ADMIN_USERNAME=admin
ADMIN_PASSWORD=please-change-this-password
```

### 启动项目

```powershell
cd package
.\venv\Scripts\activate
python .\main.py
```

启动后默认访问地址：

- 用户界面：`http://localhost:9800`
- 管理后台：`http://localhost:9800/admin`
- API 文档：`http://localhost:9800/docs`

## 打包方式

### Windows 一键打包

```powershell
cd package
.\build.ps1
```

脚本会自动完成以下步骤：

1. 检查 Python 和 Node.js
2. 创建或复用 `venv`
3. 安装 Python 依赖
4. 安装前端依赖并执行 `npm run build`
5. 复制前端产物到 `static`
6. 调用 `PyInstaller` 打包

输出文件默认位于：

```text
package/dist/AI学术写作助手.exe
```

### 打包注意事项

当前打包只包含前端静态资源和后端服务代码，构建前请确认 `.env` 配置和数据库文件位于 `dist` 或运行目录下。

## 关键配置项

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `SERVER_PORT` | 服务端口 | `9800` |
| `POLISH_MODEL` | 第一阶段润色模型 | `gpt-5` |
| `ENHANCE_MODEL` | 第二阶段增强模型 | `gpt-5` |
| `MAX_CONCURRENT_USERS` | 最大并发用户数 | `5` |
| `API_REQUEST_INTERVAL` | AI 请求间隔秒数 | `6` |
| `DEFAULT_USAGE_LIMIT` | 新卡密默认次数 | `1` |
| `SEGMENT_SKIP_THRESHOLD` | 跳过短段落阈值 | `15` |
| `USE_STREAMING` | 是否启用流式输出 | `false` |

## 常见问题

### 1. Word 导出失败

通常是以下原因之一：

- 当前机器不是 Windows
- 未安装 Microsoft Word
- 目标文档正在被占用

### 2. 端口被占用

修改 `.env` 中的 `SERVER_PORT`，或关闭占用 `9800` 端口的程序。

### 3. AI 接口调用失败

请检查：

- API Key 是否正确
- Base URL 是否为 OpenAI 兼容格式
- 后台系统配置中的模型名称是否填写正确

## License

未经允许禁止商业使用。

Creative Commons (CC BY-NC-SA 4.0)
