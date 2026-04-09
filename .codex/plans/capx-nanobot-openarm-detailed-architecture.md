# OpenArm Agent 系统详细计划 / 架构书

## 1. 文档目的

本文档用于确定以下组合方案的目标架构、边界、接口、阶段计划和验收标准：

- `nanobot` 作为外层交互壳
- `cap-x` 作为代码生成式机器人执行内核
- `openclaw_realsense_agent` 作为无 GPU 感知与触觉服务
- `Evo-RL` 作为 `OpenArm` 底层控制实现
- 动作库与动作组合封装为 LLM 可调用 API

本文档当前阶段只做方案定稿，不涉及业务代码修改。

## 2. 结论先行

推荐采用四层结构：

1. 交互层：`nanobot`
2. 编排执行层：`cap-x`
3. 机器人能力层：`OpenArmControlApi` + `OpenArmPerceptionApi` + 动作库
4. 底层设备层：`Evo-RL OpenArmFollower` + 本地感知服务

核心原则：

- 保留 `cap-x` 的 code-as-policy 主循环，不改成 tool-calling 内核
- 不让 LLM 直接操作 `Evo-RL` 底层对象
- 让 LLM 通过安全、有限、可解释的 API 来完成机器人任务
- 优先使用动作原语和动作组合，而不是让 LLM 长篇生成底层关节控制代码

## 3. 目标与约束

### 3.1 目标

1. 在无 GPU 工控机上运行真实机器人 agent。
2. 复用 `nanobot` 已验证的 API 调用链路和 App 交互能力。
3. 保留 `cap-x` 的多轮代码生成、执行、反馈、再生成机制。
4. 用你自己的感知模块替换 `cap-x` 中依赖 GPU 的视觉大模型链路。
5. 用 `Evo-RL` 的 `OpenArm` 控制接口作为真实机器人底层。
6. 用动作库提高真实机器人执行的稳定性、安全性和可维护性。

### 3.2 工程约束

1. `OpenArm` 当前依赖 Linux + CAN，总体部署应以 Linux 工控机为主。
2. LLM 通过远程 API 调用，不在本地推理。
3. 工控机无 GPU，不能依赖 SAM3、ContactGraspNet、OWL-ViT、SAM2、Molmo 本地视觉服务。
4. 真实机器人必须优先考虑安全边界、动作限幅、人工接管和故障停机。

## 4. 当前系统角色划分

### 4.1 nanobot 的角色

`nanobot` 负责：

- App/IM 入口
- 用户身份与会话
- LLM provider 配置
- 对话式任务下发
- 任务状态回报

`nanobot` 不负责：

- 机器人底层控制
- 多轮代码执行内核
- 真实机器人动作安全细节

### 4.2 cap-x 的角色

`cap-x` 负责：

- 构建 prompt
- 让 LLM 生成 Python 代码
- 执行代码
- 在失败或中间状态下继续多轮再生成
- 将 API 文档暴露给模型

`cap-x` 不负责：

- App channel
- 用户账号体系
- 实际电机驱动协议

### 4.3 openclaw_realsense_agent 的角色

负责：

- 摄像头读取
- 目标检测
- 深度定位
- 触觉读取
- 触觉健康检查

应被视为：

- 本地感知服务
- 可被 `cap-x API` 调用的外部能力

### 4.4 Evo-RL 的角色

负责：

- `OpenArmFollower` 实例化
- `get_observation()`
- `send_action()`
- CAN / 电机 / 相机连接
- 设备校准与安全限位

应被视为：

- 机器人底层驱动与设备抽象层

## 5. 目标架构

## 5.1 逻辑架构

```text
User/App
  -> nanobot
  -> Robot Bridge
  -> cap-x Runtime
  -> OpenArm APIs
  -> Action Library / Perception Client
  -> Evo-RL OpenArm + openclaw_realsense_agent
```

## 5.2 分层说明

### A. 交互层

组件：

- `nanobot gateway`
- `nanobot channels`
- `nanobot provider`

职责：

- 接收用户任务
- 将任务发送给机器人桥接层
- 接收机器人执行状态并回传

### B. 机器人执行层

组件：

- `cap-x` 运行时
- `CodeExecutionEnvBase`
- `trial` 多轮执行循环

职责：

- 根据任务构建 prompt
- 让 LLM 生成代码
- 执行 API 调用
- 根据执行结果继续再生成

### C. 能力封装层

组件：

- `OpenArmControlApi`
- `OpenArmPerceptionApi`
- `OpenArmSkillApi`
- `Action Library`

职责：

- 隐藏底层控制细节
- 暴露给 LLM 安全可用的函数集
- 聚合感知、控制、动作组合

### D. 设备层

组件：

- `Evo-RL OpenArmFollower`
- 本地检测/深度/触觉服务

职责：

- 直接连接真实机器人和传感器

## 6. 关键设计原则

### 6.1 LLM 不直接控制底层

推荐默认：

- 在真实机器人模式下，不向 LLM 暴露原始 `env`
- LLM 只能调用我们显式暴露的 API

理由：

- 提高安全性
- 降低误用风险
- 让日志和行为更可审计

### 6.2 优先中层动作原语

推荐默认：

- 暴露“可复用动作原语”
- 不暴露电机级细节

理由：

- 真实机器人上更稳定
- 更易调试
- 更符合 `cap-x` 通过 API 控制机器人的设计哲学

### 6.3 感知服务化

推荐默认：

- `openclaw_realsense_agent` 继续独立跑成本地 HTTP 服务
- `cap-x API` 通过 client 调用

理由：

- 最少改动
- 易替换
- 易单测

### 6.4 桥接而非融合

推荐默认：

- `nanobot` 和 `cap-x` 之间采用桥接
- 不把 `nanobot` agent loop 融进 `cap-x`

理由：

- 两者范式不同
- 可维护性更好
- 风险最小

## 7. 未确定事项与推荐默认值

下面是当前还没有百分之百拍板，但已经可以给出推荐默认方案的事项。

### 7.1 单臂还是双臂

未决点：

- 目标系统首期是否是单臂 `OpenArm`
- 是否马上考虑双臂

推荐默认：

- 第一阶段只做单臂

原因：

- 单臂链路更短
- 动作库更容易收敛
- 能更快验证 `nanobot + cap-x + 感知 + Evo-RL`

### 7.2 动作控制粒度

未决点：

- 直接暴露关节控制
- 还是主要暴露动作库

推荐默认：

- 主暴露动作原语
- 保留一个受限的 `move_joints_safe()` 作为兜底

原因：

- 保持灵活性
- 又不让模型长期停留在危险的低层控制

### 7.3 是否首期保留 cap-x Web UI

未决点：

- 首期是否保留 `cap-x web-ui`

推荐默认：

- 保留

原因：

- 调试时很有价值
- 不影响后续把 App 做成主入口

### 7.4 nanobot 与 cap-x 的连接方式

未决点：

- 进程内直接调用
- 子进程调用
- HTTP 服务桥接

推荐默认：

- 用本地 HTTP 服务桥接

原因：

- 边界清晰
- 便于状态查询
- 便于以后拆分部署

### 7.5 感知输出粒度

未决点：

- 当前感知服务是否只返回目标检测和深度
- 是否要扩展成直接输出抓取位姿

推荐默认：

- 第一阶段只依赖“检测 + 深度 + 触觉”

原因：

- 你现有模块已经具备
- 可先配合动作库做接近、对齐、抓取
- 后续再决定是否加入更高层 grasp pose 推断

### 7.6 运动规划方式

未决点：

- 是否保留 IK / 轨迹规划器

推荐默认：

- 第一阶段尽量不依赖复杂规划器
- 以安全动作库 + 小步闭环为主

原因：

- 无 GPU 工控机上更稳
- 适合 OpenArm 这类真实机械臂首期接入

### 7.7 并发策略

未决点：

- 是否允许多个机器人任务并发

推荐默认：

- 单机器人单活跃任务

原因：

- 真实机器人不适合并发任务竞争
- 状态管理更简单

## 8. 详细模块设计

### 8.1 Robot Bridge

建议新增一个桥接服务，位于 `nanobot` 与 `cap-x` 之间。

职责：

- 接收来自 `nanobot` 的任务
- 启动一个 `cap-x` 运行会话
- 查询执行状态
- 转发中间日志
- 支持停止 / 注入补充指令

推荐接口：

- `POST /robot/tasks/start`
- `GET /robot/tasks/{task_id}`
- `POST /robot/tasks/{task_id}/inject`
- `POST /robot/tasks/{task_id}/stop`
- `GET /robot/health`

### 8.2 OpenArm Runtime

建议封装一个 `OpenArmLowLevelEnv` 或 `OpenArmRuntime`。

职责：

- 内部持有 `Evo-RL OpenArmFollower`
- 提供统一观测
- 提供基础动作执行
- 管理连接、校准、复位、安全停机

最小能力：

- `connect()`
- `disconnect()`
- `reset_to_home()`
- `get_observation()`
- `send_joint_targets()`
- `open_gripper()`
- `close_gripper()`
- `stop_motion()`

### 8.3 Perception Client

建议从你的服务中抽出一个 `PerceptionClient`。

职责：

- 调用 `/detect_once`
- 调用 `/tactile/health`
- 调用 `/tactile/read`
- 做响应格式标准化

最小能力：

- `detect_object(target: str)`
- `get_depth_target(target: str)`
- `read_tactile()`
- `check_tactile_ready()`

### 8.4 Action Library

动作库是核心。

分三层：

#### 基础动作

- `move_joints_safe(joints)`
- `open_gripper()`
- `close_gripper()`
- `hold_position()`
- `go_home()`

#### 命名姿态动作

- `raise_hand()`
- `lower_hand()`
- `arm_to_observe_pose()`
- `arm_to_pregrasp_pose()`
- `arm_to_drop_pose()`

#### 组合动作

- `search_target(target_name)`
- `approach_target(target_name)`
- `align_to_target(target_name)`
- `descend_until_contact()`
- `grasp_with_tactile_feedback(target_name)`
- `lift_after_grasp()`

### 8.5 LLM 可见 API

建议最终暴露给模型的 API 先控制在 10 到 20 个以内。

推荐首批：

- `get_robot_state()`
- `get_camera_observation()`
- `detect_object(target_name)`
- `read_tactile()`
- `move_to_named_pose(name)`
- `move_joints_safe(joints)`
- `open_gripper()`
- `close_gripper()`
- `raise_hand()`
- `lower_hand()`
- `search_target(target_name)`
- `approach_target(target_name)`
- `align_to_target(target_name)`
- `grasp_target(target_name)`
- `lift_object()`
- `place_object(target_zone)`
- `stop_robot()`

## 9. Prompt 与 API 设计原则

### 9.1 API 文档必须偏操作指南

每个 API 文档应写清：

- 什么时候用
- 输入输出是什么
- 是否阻塞
- 安全限制
- 失败时会发生什么

### 9.2 鼓励模型做“编排”，不做“伺服”

prompt 应明确要求：

- 优先使用高层 API
- 尽量不要直接构造大段关节轨迹
- 失败时先观察再调整

### 9.3 多轮反馈聚焦状态差异

多轮反馈中重点给模型：

- 当前动作执行结果
- 是否看到目标
- 触觉是否接触
- 当前是否抓稳
- 是否回到安全姿态

## 10. 安全设计

### 10.1 硬限制

- 关节限位
- 单次相对位移限幅
- 超时自动停止
- 夹爪力度上限
- 一键停机

### 10.2 运行规则

- 同时只允许一个活跃任务
- 动作前必须检查机器人连接与校准状态
- 感知异常时不允许执行高风险动作
- 关键动作前后自动记录状态

### 10.3 人工接管

必须支持：

- 任务中止
- 人工恢复
- 重新回 home

## 11. 分阶段实施计划

### Phase 0：方案定稿

输出：

- 本架构书
- API 草案
- 动作库草案

验收：

- 边界清晰
- 未决项有默认值

### Phase 1：OpenArm 本地闭环最小版本

范围：

- 接入 `Evo-RL OpenArmFollower`
- 接入感知服务
- 实现基础动作库
- 实现 `cap-x` 单臂真实机器人 API

不做：

- `nanobot` 接入
- 多任务
- 高级规划器

验收：

- 本地能完成简单观察、接近、抓取、抬起任务

### Phase 2：cap-x 与 nanobot 桥接

范围：

- 新增 Robot Bridge
- `nanobot` 下发任务
- `nanobot` 获取状态
- 文本回报和基本中间进度

验收：

- 用户可通过 App 发任务并看到执行结果

### Phase 3：强化动作库与多轮策略

范围：

- 扩展动作组合
- 优化 prompt
- 增强失败恢复
- 加入更多触觉闭环逻辑

验收：

- 任务成功率明显提升
- 中间再规划更稳定

### Phase 4：体验统一

范围：

- 决定是否保留 `cap-x web-ui`
- 将关键执行状态结构化回传给 `nanobot`

验收：

- 调试入口和生产入口边界清晰

## 12. 验收标准

### 架构验收

- 模块边界清晰
- 真实机器人不暴露底层驱动给 LLM
- 感知与控制可独立替换

### 功能验收

- 远程 LLM 能稳定调用本地机器人
- 动作库可被 LLM 复用
- 感知服务可独立运行并返回稳定结果
- `nanobot` 可完成任务下发与状态查询

### 安全验收

- 所有动作都有安全限幅
- 失败可停止
- 人工可接管

## 13. 当前建议的默认定稿

如果现在就先定版本，我建议按下面这组默认值进入实施阶段：

1. 首期做单臂 `OpenArm`
2. `nanobot` 做外层交互壳
3. `cap-x` 保留执行内核
4. `openclaw_realsense_agent` 继续做本地感知服务
5. `Evo-RL OpenArmFollower` 做底层
6. 用本地 HTTP Robot Bridge 串联 `nanobot` 和 `cap-x`
7. 首期主打动作原语 + 动作组合，不依赖复杂 GPU 规划器
8. 保留 `cap-x web-ui` 作为研发调试入口
9. 真实机器人模式下不向 LLM 暴露原始 `env`
10. 单机器人只允许单活跃任务

## 14. 下一步建议

下一步不应立即写实现代码，而应先补两份设计清单：

1. `OpenArmControlApi` 函数清单
2. `Action Library` 动作清单与状态机

只要这两份清单定了，后面的代码改造路径就会非常清楚。
