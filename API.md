# Episcience 认证接口说明

后端基于 FastAPI，路径前缀均为 `/api/auth`。登录/注册的凭证会在前端使用 RSA 公钥加密后再发送，后端使用私钥解密，存储的是 bcrypt 哈希。

- **GET `/api/auth/public-key`**
  - 返回：`{ "public_key": "<PEM 字符串>" }`
  - 用途：前端请求后设置到 JSEncrypt，再对账号信息加密。

- **POST `/api/auth/register`**
  - 请求体：`{ "payload": "<RSA 加密后的 base64>" }`，明文 JSON 形如 `{ "username": "demo", "password": "123456", "email": "a@b.com", "full_name": "昵称" }`
  - 响应：用户信息 `UserRead`
  - 状态码：`201`

- **POST `/api/auth/login`**
  - 请求体：同上，明文 JSON 形如 `{ "username": "demo", "password": "123456" }`
  - 响应：`{ "access_token": "...", "token_type": "bearer", "user": UserRead }`

- **GET `/api/auth/me`**
  - Header：`Authorization: Bearer <token>`
  - 返回：当前用户信息

- **POST `/api/auth/logout`**
  - 返回：`{ "message": "客户端请删除本地凭证即可完成退出登录" }`

## 运行方式

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example .env  # 如需修改秘钥/数据库路径请调整
uvicorn backend.main:app --reload
```

首次启动会自动生成 RSA 密钥（默认保存在 `backend/keys/`）并创建 SQLite 数据库。
