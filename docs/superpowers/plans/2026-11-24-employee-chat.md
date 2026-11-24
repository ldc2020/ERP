# Employee Chat Implementation Plan

> 使用 superpowers:subagent-driven-development 并行实施有明确接口边界的任务，由主代理集成和最终验收。

**Goal:** 在现有 ERP 内交付可搜索添加联系人的持久化一对一文字聊天。

**Architecture:** 独立聊天模块复用当前登录和数据库。REST 与两秒轮询连接 vue-advanced-chat 2.1.2，使用标签页会话存储保持双账号独立。

**Tech Stack:** FastAPI、SQLAlchemy、PostgreSQL、Vue 3、vue-advanced-chat 2.1.2（MIT）。

**Spec:** ../specs/2026-11-24-employee-chat-design.md

## 模块与接口

后端文件 app/modules/chat/{models,schemas,service,router}.py 及 __init__.py。外部注册在 app/api/__init__.py，初始化建表在 app/scripts/initialize/main.py。
前端文件 src/modules/chat/{api.js,ChatPage.vue,useChat.js}，src/auth/storage.js。外围通过 router 和 layout 注册入口。

所有接口返回当前项目 SuccessResponse 信封 data。
- GET /api/chat/users?q=... → [{id,username,name,avatar,is_contact}]。空查询返回空数组，最大 20 人。
- GET /api/chat/contacts → [{id,user:{id,username,name,avatar,available},last_message:{id,sender_id,content,created_at}|null}]。
- POST /api/chat/contacts {user_id} → 与 contacts 单项相同的会话对象。
- GET /api/chat/conversations/{id}/messages?before_id=&after_id=&limit=50 → {items:[{id,sender_id,content,created_at,client_id}],has_more}。初始取最新50条，按 id 升序返回。before/after 互斥，单次最大100。
- POST /api/chat/conversations/{id}/messages {content,client_id:UUID} → 单条消息。同会话同发送者同 client_id 重试返回原消息。

## 任务

- [x] 后端实现并运行针对上述接口的权限、分页、并发添加和发送重试回归验证。已有库运行 init 可增加聊天表，保留原有数据。
- [x] 前端安装固定版组件，完成搜索、添加、会话与消息适配、分页、轮询及失败重试；加入清晰聊天导航。
- [x] 统一标签页登录 storage，替换全部认证引用，处理刷新请求并发及失败，保持现有账号管理行为。
- [x] 以现有管理员正常创建新普通员工，保存本地试用凭据；通过浏览器跑通双账号双向收发与刷新恢复。
- [x] 独立代码审查，修复实测问题，构建及相关回归通过，提交并提供两个页面和登录说明。

## 验收记录

- 在独立 PostgreSQL 测试库执行后端 15 项测试，均通过。覆盖并发联系人去重、消息重试、权限和历史分页，原有认证回归也通过。
- 普通员工 chat_demo 通过现有用户创建接口建立，未授予管理权限。
- 实际浏览器从 admin 搜索 chat_demo、添加联系人，通过页面的第二登录页入口登录 chat_demo。
- 两个独立标签页双向发送并收到消息，刷新后保持各自账号和消息记录；窄窗口也会自动打开聊天记录。
- 登录状态通过统一 auth 模块隔离，旧账号的延迟请求无法改用新账号身份重试。第三方许可随前端保留。
- 最终前端 18 项测试和生产构建通过。独立审查通过，覆盖轮询游标、登录切换请求隔离、重试去重和组件刷新时序。
