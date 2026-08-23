# React Web 基座

此目录引入上游 CookSleep/gpt_image_playground 的完整 React/Vite 前端，作为当前项目 Web 重构基座。

- UI 组件、布局、Lightbox、Agent、Settings、收藏夹、遮罩编辑器均来自上游结构
- 当前 `web/index.html` 暂作为兼容回退入口
- 接入当前 Python API 前，需完成 `src/lib/api.ts`、`src/lib/agentApi.ts` 和 `src/store.ts` 的兼容适配
- 构建：`npm install && npm run build`

禁止将上游前端直接请求当前 Provider；必须经过当前项目 `/v1/*` 适配层。
