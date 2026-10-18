# 协作规范（CONTRIBUTING）

本项目由多人协作维护。为保证提交可追溯、避免冲突与密钥泄露，请所有协作者遵循以下规范。

## 一、一次性初始化

### 1. 配置自己的 Git 身份

必须使用**你本人**的 GitHub 用户名与邮箱，**切勿共用他人身份**（否则提交无法归属到你的账号）：

```bash
git config --global user.name  "你的GitHub用户名"
git config --global user.email "你的GitHub邮箱"
```

> 邮箱需与你的 GitHub 账号关联，提交头像与贡献图才会正确显示。

### 2. 配置 SSH 密钥

```bash
ssh-keygen -t ed25519 -C "你的邮箱"
# 将 ~/.ssh/id_ed25519.pub 的内容添加到 GitHub → Settings → SSH and GPG keys
```

### 3. 克隆仓库

```bash
git clone git@github.com:XieTianYi486/Multi-agent-collaborative-crawling-of-knowledge-base.git
cd Multi-agent-collaborative-crawling-of-knowledge-base
```

### 4. 配置环境变量

```bash
cd backend
cp .env.example .env      # 填入你自己的 DASHSCOPE_API_KEY 等
```

### 5. 获取知识库数据

KB 主库与向量索引**不随仓库分发**，需向项目管理员索取（详见 README「知识库数据获取」一节）。



## 二、日常协作流程

**禁止直接向 `main` 推送**，一律走 分支 → Pull Request 流程：

```bash
git pull                       # 开工前先拉取最新
git switch -c feature/xxx      # 建自己的分支
# ... 开发 ...
git add <具体文件>              # 按文件添加，不要盲目 git add -A
git commit -m "feat: xxx"
git push -u origin feature/xxx
```

推送后到 GitHub 发起 Pull Request，由项目所有者审核合并。

- **分支命名**：`feature/功能名`、`fix/问题名`、`docs/文档名`
- **提交信息**：`<类型>: <中文简述>`，类型取 `feat` / `fix` / `docs` / `refactor` / `chore` / `test`



## 三、绝对不要提交的内容

| 禁止提交 | 原因 |
|----------|------|
| `.env`、任何含 API Key 的文件 | 机密泄露。已被 `.gitignore` 忽略，勿用 `-f` 强行加入 |
| `*.db`（含 `backend/data/enterprise_rag.db`） | 运行期二进制，无法合并，且可能夹带爬取内容中的密钥 |
| `backend/chroma_data/`、`node_modules/`、`frontend/dist/` | 体积巨大，属可重建的派生产物 |

> 仓库已开启 GitHub **Push Protection**：提交中一旦检测到密钥（如 `sk-...`）会直接拦截推送。若不慎把密钥写进代码或文档，务必从提交中移除，并**立即到服务商后台轮换/吊销该密钥**。



## 四、常见问题

**拉取时报冲突**

```bash
git pull --rebase        # 把自己的提交重放到最新 main 之上
# 解决冲突后
git add <冲突文件>
git rebase --continue
```

**误提交了密钥**

1. 若尚未推送：用 `git commit --amend` 或 `git reset` 移除后再提交
2. 若已推送：除修改提交外，**立即轮换/吊销该密钥**（历史记录中的密钥应视为已泄露）
3. 若被 Push Protection 拦截：按提示从历史中移除密钥，不要走"允许该密钥"的绕过通道

**想撤销最近一次提交但保留改动**

```bash
git reset --soft HEAD~1
```
