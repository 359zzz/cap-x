# CaP-X + nanobot + 自定义感知模块改造讨论稿

## 目标

1. 在无 GPU 的工控机上运行机器人 agent。
2. 保留 `cap-x` 的整体控制架构与代码执行式 agent 主循环。
3. 去掉 `cap-x` 中依赖本地 GPU 推理的感知/大模型模块。
4. 用已有的 `openclaw_realsense_agent` 感知与触觉服务替换相应模块。
5. 复用 `nanobot` 已经打通的 LLM API 调用与 App 交互能力。

## 当前项目观察

### CaP-X

- `capx/envs/trial.py` 的核心是：
  - LLM 生成 Python 代码
  - 在 `CodeExecutionEnvBase` 中执行
  - 通过 API 函数操作机器人
- `capx/envs/tasks/base.py` 说明 API 是第一等接口：
  - LLM 看到的是 `functions()` 里的函数签名和 docstring
  - 因此非常适合通过“新增/替换 API 类”接入你的模块
- `capx/llm/client.py` 已支持 OpenAI-compatible `/chat/completions`
  - 说明 LLM 本身并不要求本地 GPU
- 真正依赖 GPU 的主要是感知/规划服务：
  - `SAM3`
  - `ContactGraspNet`
  - `SAM2`
  - `OWL-ViT`
  - `Molmo` 本地视觉指点服务
  - 部分场景下的 `cuRobo`
- `PyRoKi` 在当前结构里是独立远程服务，可保留或后续再替换。

### nanobot

- `nanobot` 的强项是：
  - 多渠道 App 入口
  - Provider 抽象
  - 已验证的 API 调用配置
  - Gateway / Channel / Session 管理
- `nanobot/providers/custom_provider.py` 可以直接对接 OpenAI-compatible API。
- `nanobot/cli/commands.py` + `nanobot/channels/manager.py` 已把：
  - LLM provider
  - App channel
  - agent loop
  - gateway
 组织成了一个稳定的上层交互框架。
- 但 `nanobot` 的 agent 主循环是“对话 + tool calling”范式，不是 `cap-x` 的“代码生成 -> 执行 -> 多轮再生成”范式。
- 所以它不适合作为 `cap-x` 内核的直接替代，更适合作为上层交互壳。

### openclaw_realsense_agent

- 你的模块已经是很好的“本地服务化感知层”：
  - `app/service/main.py` 暴露了 `/detect_once`、`/tactile/read`、`/tactile/health`
  - `app/agent/service_client.py` 已经有稳定 HTTP client
- 它的接口风格与 `cap-x` 现有远程感知服务非常接近：
  - 都是本地 HTTP 服务
  - 都是控制 API 内部去调用
- 这意味着它天然适合替代 `cap-x` 当前的视觉/触觉入口。

## 推荐方案

推荐采用“双层架构”，而不是把两个项目硬揉成一个 agent 内核。

### 外层：nanobot 负责人机交互

- 继续使用 `nanobot` 的：
  - provider 配置
  - App channel
  - gateway
  - 会话管理
- 用户通过 App 给机器人下任务。
- nanobot 不直接做底层机器人控制，而是调用一个“机器人运行时接口”。

### 内层：cap-x 负责机器人任务执行

- 保留 `cap-x` 的：
  - `trial` 主循环
  - 代码生成与多轮再生成机制
  - `CodeExecutionEnvBase`
  - 低层环境与控制接口
- 把改造集中在 API 层和配置层，而不是重写 agent 核心。

### 感知替换：用你的服务替代 GPU 模块

- 新增一个 CPU 友好的控制/感知 API 类，例如：
  - `OpenClawPerceptionApi`
  - 或 `R1ProControlApiCpu`
  - 或 `FrankaRealControlApiCpu`
- 这个 API 类内部通过 HTTP 调你的服务：
  - `detect_once`
  - `tactile_read`
  - 后续如果你扩展，也可以接 `estimate_grasp_pose` / `get_target_pose`
- 这样可以把以下模块从 YAML 和 API 初始化中移除：
  - SAM3
  - ContactGraspNet
  - SAM2
  - OWL-ViT
  - Molmo

### 保留控制骨架

- 低层控制尽量保持：
  - 机械臂控制
  - move / gripper / IK / navigation
  - 任务执行与多轮反馈
- 如果 `PyRoKi` 在工控机 CPU 上可接受，则先保留。
- 如果 `PyRoKi` 也过重，再第二阶段替换成你现有机器人控制模块或更轻量 IK/轨迹模块。

## 最推荐的落地路径

### Phase 1：最小可行集成

- 不碰 `cap-x` 的 trial 主循环。
- 新增一个 API 类，内部只调用你的感知服务。
- 新建一套 YAML：
  - 不启动 `SAM3` / `GraspNet` / `SAM2` / `OWL-ViT`
  - 只保留必须的低层服务
- 用 `cap-x` 直接跑通“远程 LLM + 本地轻量感知 + 原控制骨架”。

目标：
- 先证明 `cap-x` 在无 GPU 条件下仍能完成基本任务闭环。

### Phase 2：接入 nanobot 作为上层入口

- 给 `nanobot` 增加一个机器人工具或独立桥接服务：
  - `start_robot_task`
  - `get_robot_status`
  - `inject_robot_instruction`
  - `stop_robot_task`
- 用户继续通过 App 与 `nanobot` 交互。
- `nanobot` 把任务转给 `cap-x` 运行时。

目标：
- 复用已有 App 通道与 API 配置，不把聊天能力和机器人执行逻辑耦死。

### Phase 3：统一会话与状态反馈

- 把 `cap-x` 的执行日志、视觉结果、关键中间状态回传给 `nanobot`。
- 决定是否保留 `cap-x web-ui`：
  - 保留：用于调试和研究
  - 不保留：App 成为唯一交互入口

## 不推荐的方案

### 不推荐方案 A：直接把 nanobot agent loop 替换 cap-x trial loop

原因：
- 两者范式不同
- 需要重写 `cap-x` 多轮代码执行逻辑
- 风险大，收益小

### 不推荐方案 B：把 cap-x 整体迁移成 nanobot tool-calling 机器人

原因：
- 这会丢掉你明确想保留的 `cap-x` 控制架构
- 首期工作量大
- 调试难度显著增加

## 当前最大不确定点

1. 你要保留的是 `Franka` 路线、`R1Pro` 路线，还是另一个真实机器人低层？
2. 你的 `openclaw_realsense_agent` 目前输出的是：
   - 仅检测 + 触觉
   - 还是还能稳定给出 3D 位姿 / 抓取候选
3. 工控机上 `PyRoKi` 是否可接受：
   - 如果可接受，第一阶段改造会明显更轻
   - 如果不可接受，需要把运动规划也一起替换
4. App 交互优先级：
   - 是先要“App 下发任务 + 文本回报”
   - 还是一开始就要“App 中实时看到执行状态”

## 结论

最稳妥的做法是：

- `nanobot` 负责“人与机器人对话”
- `cap-x` 负责“机器人任务执行”
- 你的 `openclaw_realsense_agent` 负责“无 GPU 感知与触觉”

先把 `cap-x` 的 GPU 感知链路替换掉，再把 `nanobot` 接到 `cap-x` 外层做任务入口。这条路径改动面最小，也最符合你“保留 cap-x 控制架构、复用 nanobot API 与 App”的目标。
