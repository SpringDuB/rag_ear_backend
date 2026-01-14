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

## 文件/文件夹接口（FileSystem）

路径前缀：`/api/fs`，均需要登录态：

- Header：`Authorization: Bearer <token>`

- **POST `/api/fs/folders`**（新建文件夹）
  - 请求体：`{ "name": "xxx", "parent_id": 1 }`（`parent_id` 可为空表示根目录）
  - 返回：`FolderRead`

- **PATCH `/api/fs/folders/{folder_id}`**（重命名/移动文件夹）
  - 请求体：`{ "name": "新名字", "parent_id": 2 }`
  - 说明：`parent_id=null` 表示移动到根目录；禁止移动到自身或其子文件夹内
  - 返回：`FolderRead`

- **DELETE `/api/fs/folders/{folder_id}`**（删除文件夹，递归删除子内容）
  - 返回：`{ "deleted": <数量> }`

- **GET `/api/fs/root/children`**（列出根目录内容）
  - 返回：`{ "folders": FolderRead[], "files": FileRead[] }`

- **GET `/api/fs/folders/{folder_id}/children`**（列出指定文件夹内容）
  - 返回：同上

- **POST `/api/fs/files`**（上传文件）
  - `multipart/form-data`
    - `file`: 上传文件
    - `folder_id`: 可选，目标文件夹 id；为空表示根目录
  - 返回：`FileRead`

- **GET `/api/fs/files/{file_id}`**（查看文件元数据）
  - 返回：`FileRead`

- **PATCH `/api/fs/files/{file_id}`**（重命名/移动文件）
  - 请求体：`{ "name": "新文件名.pdf", "folder_id": 1 }`
  - 说明：`folder_id=null` 表示移动到根目录
  - 返回：`FileRead`

- **DELETE `/api/fs/files/{file_id}`**（删除文件：删磁盘内容 + 删库记录）
  - 返回：`{ "deleted": 1 }`

- **GET `/api/fs/files/{file_id}/download`**（下载文件）
  - 返回：文件流（带 `filename`）
