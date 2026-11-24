# ERP 管理底座

每家客户部署一套应用、PostgreSQL 和 Redis。仓库基于
[fastapi-vue-admin 86d2479](https://github.com/SenQi-666/fastapi-vue-admin/tree/86d247981b43ef89c139c2e913a0e6f6f678e212)，
保留 [MIT 许可和版权声明](LICENSE)。

## 运行依赖

Docker Engine 与 Docker Compose v2。应用镜像使用 Python 3.12、Node.js 22 和 Nginx，
数据服务使用 PostgreSQL 16 和 Redis 7。前端依赖由 `web/package-lock.json` 锁定，
后端依赖位于 `backend/requirements.txt`。

## 新客户部署

将下例中的 `baini` 替换为该客户唯一的 Compose 项目名。为每个项目创建独立配置目录，
以便分别管理凭据和备份。以下命令在仓库根目录执行。

```sh
mkdir -p .deploy/baini
chmod 700 .deploy/baini
umask 077
cp .env.example .deploy/baini/.env
```

编辑 `.deploy/baini/.env`，为 `ERP_DB_PASSWORD` 和 `ERP_SECRET_KEY` 分别生成独立值，
例如分别运行一次 `openssl rand -hex 32`。数据库密码使用十六进制字符。
同一主机上第二套部署应另选 `ERP_PORT`，例如 `5181`。默认地址仅对本机开放，
对外访问时可在宿主机反向代理上配置 HTTPS。

先构建镜像，使用管理员凭据初始化空数据库，再启动服务。
初始密码至少需 12 个字符，上限为 72 个 UTF-8 字节。以下命令在 POSIX shell 中读取口令。

```sh
erp() {
  docker compose -p baini --env-file .deploy/baini/.env "$@"
}

erp build
printf '初始管理员密码: '
stty -echo
read -r ADMIN_PASSWORD
stty echo
printf '\n'
export ADMIN_PASSWORD
if erp run --rm -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD backend python main.py init; then
  unset ADMIN_PASSWORD
  erp up -d
else
  unset ADMIN_PASSWORD
fi
```

打开 [ERP 登录页](http://127.0.0.1:5180)，用初始化时指定的管理员账号和密码登录。
可通过 [API 文档](http://127.0.0.1:5180/docs) 核对本实例的接口。
用 `erp ps` 查看状态，用 `erp logs backend` 检查启动日志。
关闭应用时用 `erp down`，数据库保存在项目专属的命名卷中。

第二家客户使用另一组项目名、配置目录、端口及独立凭据执行同样的流程。
Compose 项目名决定独立网络与数据卷，避免在不同部署间复用项目名。
升级前先备份各实例的 PostgreSQL 数据。数据库初始化用于新实例。

## 客户专属模块

客户实例保有独立应用配置和数据库。新增业务能力时，在后端建立独立路由模块，前端建立相应页面，
通过该模块自己的权限与路由接入管理端。共同账号、角色和审计逻辑留在核心模块中。

## 员工聊天

聊天界面复用 [vue-advanced-chat 2.1.2](https://github.com/advanced-chat/advanced-chat-components/tree/v2)，
随前端分发的许可位于 `web/public/licenses/vue-advanced-chat.txt`。

后端模块位于 `backend/app/modules/chat`，前端模块位于 `web/src/modules/chat`。
登录标签页隔离由 `web/src/auth/storage.js` 统一处理。聊天沿用本实例的员工账号和数据库。
新库与已有数据库都需运行 `python main.py init` 创建聊天表，已有账号与资料会保留。

登录后打开“聊天”，按账号或姓名搜索启用的员工，点击添加即可建立双方可见的联系人会话。
每个标签页独立登录，刷新保留该页账号。聊天页提供第二登录页入口。
消息保存到 PostgreSQL，每两秒同步新消息，发送失败后可使用同一消息标识重试。

`chat_demo` 是本机验收时通过账号管理接口创建的普通员工。
其凭据只保存在本机忽略目录 `.deploy/local-preview`，新客户初始化时由管理员创建员工。
