# Cap-X OpenArmControlApi / 动作库 / 录制执行方案定稿

## 1. 本文档要解决的问题

在以下约束下，定下首期可实施的控制接口与动作体系：

- 双臂 `OpenArm`
- 保留 `cap-x` 执行内核与 `web-ui`
- 只允许单活跃任务
- 不做仿真，直接上实机
- 优先动作原语，小步闭环
- 受限关节控制只作为辅助手段
- 录制能力也要集成到 `cap-x`
- `nanobot`、OpenArm 低层控制所需模块最终集成进 `cap-x`，但内部保持解耦

本文重点回答四件事：

1. `OpenArmControlApi` 应该有哪些函数
2. 动作原语与动作组合应该如何分层
3. 动作录制系统如何设计
4. 调用一个动作 API 时，运行时到底应该“回放录制数据”还是“执行别的方法”

## 2. 总结结论

结论先行：

- 首期在线执行的主路径，不应该是“直接回放整段录制数据集”
- 首期在线执行的主路径，应该是“参数化动作技能 + 小步闭环 + 守卫条件”
- 录制数据的主要作用，不是直接拿来当在线动作 API，而是：
  - 生成命名姿态
  - 提取关键路点
  - 标定速度、夹爪阈值、接触阈值、时序
  - 生成技能模板
  - 为后续模仿学习/复杂策略做数据积累
- 数据集整段回放只保留为：
  - 调试工具
  - 标定工具
  - 演示复现工具
  - 离线分析工具

换句话说：

- `raise_hand()` 这种 API 不应理解成“找到某条 episode 然后整段播出来”
- 它应理解成“执行一个命名技能，这个技能内部可用录制提取出的路点/参数，但运行时仍要根据当前观测、触觉、守卫条件来闭环执行”

## 3. 模块边界

建议在 `cap-x` 内部形成以下模块：

### 3.1 对 LLM 暴露层

- `OpenArmControlApi`
- `OpenArmPerceptionApi`
- `OpenArmTaskApi`

这层的职责是：

- 给 `cap-x` 的代码生成环境提供清晰的函数签名和 docstring
- 只暴露安全、有限、可解释的能力

### 3.2 技能执行层

- `OpenArmSkillRuntime`
- `OpenArmSkillRegistry`
- `OpenArmSkillGuards`
- `OpenArmMotionTemplates`

这层的职责是：

- 接收 API 调用
- 查技能定义
- 检查前置条件
- 执行技能状态机
- 在每个小步中读取观测/触觉
- 满足停止条件后退出

### 3.3 设备运行时层

- `OpenArmRuntime`
- `OpenArmBimanualDriver`
- `OpenArmRecorder`
- `OpenArmReplayTool`

这层的职责是：

- 封装仓库内嵌的双臂 `OpenArm` 控制代码
- 屏蔽 CAN、设备连接、观测读取、动作发送
- 统一录制、回放、状态读取

### 3.4 感知层

- `OpenClawPerceptionClient`
- `TactileClient`

这层的职责是：

- 对接你的 `openclaw_realsense_agent`
- 返回标准化检测、深度、目标位姿估计、触觉信息

## 4. OpenArmControlApi 分层

不建议把所有函数都直接给 LLM。建议分三层：

### 4.1 L0：系统内部层，不直接给 LLM

这层主要服务于技能执行器和录制系统。

建议函数：

- `connect()`
- `disconnect()`
- `power_on()`
- `power_off()`
- `ensure_calibrated()`
- `emergency_stop()`
- `clear_fault()`
- `set_mode(mode)`
- `get_runtime_state()`
- `get_joint_state(arm)`
- `get_ee_pose(arm)`
- `send_joint_positions(left=None, right=None, blocking=True, speed_scale=...)`
- `send_gripper_position(arm, width, force=None, blocking=True)`
- `stop_motion()`
- `hold_position()`
- `wait_until_idle(timeout_s)`
- `read_tactile(arm=None)`
- `get_latest_detection()`
- `capture_observation()`

说明：

- 这层是硬件运行时层，不建议直接让 LLM 调
- 其中 `send_joint_positions()` 继续沿用双臂 `left_joint_i.pos` / `right_joint_i.pos` 这类 action schema

### 4.2 L1：受限控制层，可少量暴露给 LLM

这层是“兜底层”，只在动作原语不够时使用。

建议函数：

- `get_robot_state()`
- `get_observation()`
- `get_dual_arm_pose()`
- `move_to_named_pose(name, speed="normal")`
- `move_arm_to_named_pose(arm, name, speed="normal")`
- `move_joints_safe(left_joints=None, right_joints=None, speed="slow")`
- `move_arm_joints_safe(arm, joints, speed="slow")`
- `shift_arm_cartesian_safe(arm, dx=0, dy=0, dz=0, frame="base", speed="slow")`
- `open_gripper(arm, width="full")`
- `close_gripper(arm, force="gentle")`
- `set_gripper_width(arm, width)`
- `go_home()`
- `go_safe_standby()`
- `stop_robot()`

设计原则：

- 所有位移都限幅
- 所有速度都限档
- 所有阻塞调用都带超时
- 默认进入安全姿态再切动作

### 4.3 L2：解剖学 / 空间语义动作原语层，首期主要暴露给 LLM

这是首期真正的主力层。

这一层不再以 `pick_target()` 这类任务语义为主，而是以“身体部位 + 动作方向 + 程度 + 空间语义”为主。

推荐 API 形态：

- `get_motion_primitive_catalog()`
- `execute_motion_primitive(arm, primitive, magnitude="medium", speed="normal")`
- `execute_bimanual_primitive(primitive, magnitude="medium", symmetry="mirror", speed="normal")`
- `undo_last_motion(arm)`

其中：

- `primitive` 是受限枚举值，不能让 LLM 自由造词
- `magnitude` 建议固定为：
  - `slight`
  - `small`
  - `medium`
  - `large`
- `symmetry` 用于双臂镜像动作

推荐首批 `primitive` 词汇：

- `raise_upper_arm`
- `lower_upper_arm`
- `open_upper_arm`
- `close_upper_arm`
- `lift_forearm`
- `lower_forearm`
- `rotate_forearm_in`
- `rotate_forearm_out`
- `wrist_in`
- `wrist_out`
- `wrist_forward_up`
- `wrist_backward_up`
- `open_gripper`
- `close_gripper`

设计原则：

- 原语一定是“有限词表”
- 每个原语都要带清晰空间语义说明
- 每个原语都要定义逆动作或恢复动作
- 同一个 `magnitude` 在不同原语上不要求角度完全一致，而是各自标定

### 4.4 L3：组合动作 / 姿态层，可暴露给 LLM

这一层是“命名组合动作”，本质上是多个 L2 原语的稳定组合。

推荐 API 形态：

- `get_motion_combo_catalog()`
- `execute_motion_combo(name, arm=None, magnitude="medium", speed="normal")`

推荐首批 `combo`：

- `hand_to_chest`
- `hand_forward_present`
- `elbow_fold_rest`
- `wrist_upright`
- `wrist_inward_ready`
- `arm_half_open`
- `arm_full_open`
- `handover_give_ready`
- `handover_receive_ready`
- `both_arms_open`
- `both_hands_to_chest`
- `both_arms_forward_ready`

原则：

- LLM 优先调用 L2/L3
- LLM 不直接写大段关节循环
- 面向物体的任务组合，例如 `pick_target()`，放到第二阶段再叠加在 L2/L3 之上

## 5. 推荐首期对 LLM 暴露的最小函数清单

首期建议严格控制数量，并把重心放在“有限动作词表”上。

### 5.1 状态与感知

- `get_robot_state()`
- `get_observation()`
- `read_tactile(arm=None)`
- `detect_target(target_name)`
- `get_target_pose(target_name)`

### 5.2 动作词表与组合词表

- `get_motion_primitive_catalog()`
- `get_motion_combo_catalog()`
- `execute_motion_primitive(arm, primitive, magnitude="medium", speed="normal")`
- `execute_bimanual_primitive(primitive, magnitude="medium", symmetry="mirror", speed="normal")`
- `execute_motion_combo(name, arm=None, magnitude="medium", speed="normal")`
- `undo_last_motion(arm)`

### 5.3 受限控制兜底

- `move_to_named_pose(name, speed="normal")`
- `move_arm_joints_safe(arm, joints, speed="slow")`
- `open_gripper(arm, width="full")`
- `close_gripper(arm, force="gentle")`
- `go_home()`
- `go_safe_standby()`
- `stop_robot()`

说明：

- 如果后面进入感知抓取阶段，再增加 `approach_target()`、`descend_until_contact()` 这一类物体交互原语
- 但在你现在这版思路里，首期主语义应该是“解剖学动作词汇”和“空间姿态组合”

## 6. 命名姿态与空间语义锚点清单

这一层不是“最终任务动作”，而是给原语和组合动作提供参考起点与目标区域。

### 6.1 双臂全局锚点

- `home`
- `safe_standby`
- `observe_front`
- `observe_top`
- `record_ready`
- `handover_center`
- `maintenance`

### 6.2 单臂中性锚点

- `left_neutral_relaxed`
- `left_neutral_ready`
- `right_neutral_relaxed`
- `right_neutral_ready`

### 6.3 单臂空间目标锚点

- `left_chest_front`
- `right_chest_front`
- `left_front_mid`
- `right_front_mid`
- `left_front_high`
- `right_front_high`
- `left_side_open`
- `right_side_open`
- `left_handover_give`
- `right_handover_give`
- `left_handover_receive`
- `right_handover_receive`

### 6.4 腕部姿态锚点

- `left_wrist_upright`
- `right_wrist_upright`
- `left_wrist_inward_ready`
- `right_wrist_inward_ready`

说明：

- 这些姿态优先通过录制/示教得到
- 这些姿态既可以作为独立动作，也可以作为组合动作中的中间检查点

## 7. 动作原语词汇清单

建议按“解剖学部位 + 空间语义 + 程度等级”的标准来设计。

### 7.1 原语定义建议

每个原语都应包含以下信息：

- `primitive_name`
- `human_alias`
- `affected_joints`
- `spatial_semantics`
- `supported_magnitudes`
- `nominal_joint_delta`
- `nominal_ee_delta`
- `inverse_primitive`
- `allowed_start_regions`
- `guard_conditions`

这里的关键是：

- `spatial_semantics` 是给 LLM 看的
- `nominal_joint_delta` 和 `nominal_ee_delta` 是给执行器用的

### 7.2 程度等级建议

建议统一四档：

- `slight`：轻微修正级
- `small`：小幅调整级
- `medium`：常规姿态切换级
- `large`：显著动作级

注意：

- 同一个 `medium` 不要求在所有原语上对应同样角度
- 每个原语都单独标定自己的幅度表

### 7.3 大臂类原语

- `raise_upper_arm`
  空间语义：整条手臂向身体前上方抬起，手部通常会向前上移动
- `lower_upper_arm`
  空间语义：整条手臂向身体后下方回落
- `open_upper_arm`
  空间语义：上臂向身体外侧张开，手部向侧前外侧移动
- `close_upper_arm`
  空间语义：上臂向身体中线内收，手部向胸前/身体内侧靠近

### 7.4 小臂类原语

- `lift_forearm`
  空间语义：肘部弯曲，小臂抬起，手更靠近胸前
- `lower_forearm`
  空间语义：肘部展开，小臂向前下方伸展
- `rotate_forearm_in`
  空间语义：前臂向身体内侧旋转，掌心或夹爪朝向更偏内侧
- `rotate_forearm_out`
  空间语义：前臂向身体外侧旋转，掌心或夹爪朝向更偏外侧

### 7.5 腕部类原语

- `wrist_in`
  空间语义：腕部朝身体中线方向内收
- `wrist_out`
  空间语义：腕部朝身体外侧张开
- `wrist_forward_up`
  空间语义：腕部前抬，手端朝前上方翘起
- `wrist_backward_up`
  空间语义：腕部后抬，手端朝后上方翘起

### 7.6 夹爪类原语

- `open_gripper`
  空间语义：张开手爪，给抓取或让渡留空间
- `close_gripper`
  空间语义：收拢手爪，用于抓取、夹持或固定

### 7.7 双臂镜像类原语

- `both_open_upper_arms`
  空间语义：双臂同时向外张开
- `both_close_upper_arms`
  空间语义：双臂同时向中间合拢
- `both_raise_upper_arms`
  空间语义：双臂同时向前上抬起
- `both_lift_forearms`
  空间语义：双臂同时屈肘，使双手更靠近胸前

## 8. 组合动作清单

组合动作不直接面向“拿取物体”，而是先面向“姿态语义”和“可复用身体动作”。

### 8.1 单臂姿态组合

- `hand_to_chest`
  空间语义：将指定侧手部移动到身体前方胸口区域
- `hand_forward_present`
  空间语义：将手向身体前方递出，适合展示、接物、试探接近
- `elbow_fold_rest`
  空间语义：回到较收拢、较放松的肘部姿态
- `wrist_upright`
  空间语义：将腕部调整到较接近“立腕”的姿态
- `wrist_inward_ready`
  空间语义：将腕部调整到适合向内取物或贴近身体操作的姿态
- `arm_half_open`
  空间语义：单臂向身体侧前方半打开
- `arm_full_open`
  空间语义：单臂明显向身体外侧张开

### 8.2 双臂姿态组合

- `both_hands_to_chest`
  空间语义：双手都收到胸前区域
- `both_arms_open`
  空间语义：双臂同时外展，形成更开阔的操作空间
- `both_arms_forward_ready`
  空间语义：双臂同时前举到便于接触前方物体的位置
- `handover_give_ready`
  空间语义：出物臂到达中心让渡区域的预备姿态
- `handover_receive_ready`
  空间语义：接物臂到达中心接收区域的预备姿态

### 8.3 第二阶段再叠加的任务组合

下面这些建议第二阶段再建立在上面的动作词汇之上：

- `approach_target()`
- `descend_until_contact()`
- `pick_target()`
- `place_to_zone()`
- `handover_transfer()`

## 9. 单活跃任务机制

由于你要求只允许单活跃任务，建议在运行时加入强约束：

- 全局 `task_lock`
- 每个技能执行期间，新的任务不能抢占
- 只允许以下控制操作越权进入：
  - `stop_robot()`
  - `emergency_stop()`
  - `get_robot_state()`
- 允许“当前任务内”发起子动作，但不允许并行执行两个技能

建议状态机：

- `IDLE`
- `RUNNING`
- `PAUSED_MANUAL`
- `STOPPING`
- `FAULT`

## 10. 动作录制设计

## 10.1 录制目标不是单一“数据集”

录制系统建议输出三类产物，而不是只输出一个 episode 文件：

### A. 原始时序数据

用于复现与分析：

- 双臂关节角
- 夹爪状态
- 相机图像
- 触觉数据
- 时间戳
- 任务标签
- 操作者标识
- episode 成败

### B. 技能资产

用于在线执行：

- 命名姿态
- 原语幅度表
- 原语关节增量模板
- 原语末端空间位移包络
- 组合动作原语序列
- 中间锚点
- 守卫阈值
- 恢复动作

### C. 技能元数据

用于注册与搜索：

- 技能名
- 适用 arm
- 动作类别
- 允许起始区域
- 目标空间区域
- 前置条件
- 风险等级
- 参数 schema
- 默认参数
- 版本号

## 10.2 录制模式建议分四种

### 模式 1：中性姿态 / 锚点录制

用途：

- 保存 `home`、`observe_front`、`left_neutral_ready`、`left_chest_front` 这类静态姿态和空间锚点

产物：

- 单帧或少量帧的姿态模板
- 该姿态下的关节值
- 该姿态下的末端位姿
- 可选的触觉/视觉基线

### 模式 2：原语幅度录制

用途：

- 针对每个原语分别录制 `slight/small/medium/large`
- 例如：
  - `raise_upper_arm`
  - `open_upper_arm`
  - `lift_forearm`
  - `wrist_in`

产物：

- 从某个中性锚点出发的关节增量模板
- 对应的末端空间位移估计
- 建议速度
- 允许起始区域
- 守卫阈值

这是你这套动作词汇体系里最关键的录制模式。

### 模式 3：组合动作录制

用途：

- 录制 `hand_to_chest`
- 录制 `wrist_upright`
- 录制 `both_arms_open`
- 录制 `handover_receive_ready`

产物：

- 原语序列
- 原语之间的检查点
- 中间锚点
- 组合动作完成判据

### 模式 4：任务录制

用途：

- 完整记录一次 `pick_and_place`
- 或完整记录一次双臂交接
- 用于分析、回放、后续训练

产物：

- episode 级数据

建议首期最重视模式 1、模式 2、模式 3。

## 10.3 当前内嵌 driver 继承了哪些低层思路

可优先复用并集成的内容：

- 设备连接与双臂 action/observation schema
- `recording_loop` 的定时采样与 episode 管理逻辑
- 录制时的图像/状态/动作同步写盘逻辑
- `replay` 的动作回放工具

但不建议照搬其“回放 = 在线执行策略”。

## 11. 调用动作 API 后，这个动作到底该怎么执行

这是最关键的定稿点。

建议采用下面这条执行链路：

```text
LLM 调用 API
-> API 解析原语名 / 组合名 / 参数
-> SkillRegistry 查到技能定义
-> SkillRuntime 检查前置条件
-> 载入该动作的模板资产（锚点/关节增量/空间语义/阈值）
-> 逐阶段执行状态机
-> 每个阶段读取当前观测 / 触觉 / 机器人状态
-> 满足守卫条件则进入下一阶段
-> 失败则恢复或退出
-> 返回结构化执行结果
```

### 11.1 一个技能的推荐内部结构

每个技能定义建议包含：

- `name`
- `description`
- `parameters_schema`
- `preconditions`
- `required_anchor`
- `motion_type`
- `phases`
- `success_conditions`
- `failure_conditions`
- `recovery_strategy`
- `recording_assets`

对于你现在这套设计，建议把动作分成三种执行类型：

### A. 锚点姿态执行

例如：

- `move_to_named_pose("left_chest_front")`
- `move_to_named_pose("right_wrist_upright")`

执行方式：

- 直接从姿态资产读取目标关节
- 采用受限阻塞执行
- 到位后做状态确认

### B. 原语增量执行

例如：

- `execute_motion_primitive("left", "raise_upper_arm", "medium")`

执行方式：

1. 识别当前 arm 所在起始区域
2. 选择最近的中性锚点或允许起始锚点
3. 读取该原语在该锚点下的 `medium` 关节增量模板
4. 分成若干小步执行
5. 每一步检查：
   - 关节限位
   - 速度限幅
   - 意外触碰
   - 当前姿态偏差
6. 完成后返回实际执行到的关节变化和空间变化

### C. 组合动作执行

例如：

- `execute_motion_combo("hand_to_chest", arm="left", magnitude="medium")`

执行方式：

1. 展开为一串原语
2. 在相邻原语之间设置检查点
3. 必要时插入中间锚点
4. 逐个原语执行
5. 最后检查是否到达目标空间区域

所以在线执行的核心不是“回放一条整轨迹”，而是：

- 锚点姿态
- 原语增量模板
- 组合动作状态机

### 11.2 为什么不建议“整段回放数据集”

原因有六个：

1. 实机初始状态每次都不一样
2. 目标位置每次都不一样
3. 双臂误差会累积
4. 夹爪接触时机不一样
5. 触觉反馈需要在线判断
6. 一旦中间偏了，整段回放没有恢复能力

所以：

- “整段 episode 回放”只适合高度固定、夹具化、重复工位
- 而你现在的方向是 agent 机器人，应该保留在线感知和小步修正能力

### 11.3 推荐的混合方案

动作执行采用“模板 + 闭环”混合方式：

- 模板给：
  - 中性锚点
  - 原语幅度表
  - 组合动作原语序列
  - 推荐速度
  - 守卫阈值
- 闭环负责：
  - 当前起始区域判断
  - 执行中姿态偏差修正
  - 意外触碰检测
  - 是否提前停止
  - 是否回退到恢复姿态

这是最适合你当前“动作库 + 小步闭环，复杂规划放后面”的路线。

## 12. 一个具体例子：`举左手到胸前`

建议 `execute_motion_combo("hand_to_chest", arm="left", magnitude="medium")` 的执行逻辑如下：

1. 判断左臂当前是否处于允许起始区域，例如 `left_neutral_relaxed` 或 `left_neutral_ready`
2. 如果不在允许区域，先切到最近的允许锚点
3. 展开 `hand_to_chest` 的原语序列，例如：
   - `raise_upper_arm(small)`
   - `lift_forearm(medium)`
   - `close_upper_arm(slight)`
   - `wrist_upright(slight)`
4. 每个原语都按小步执行，而不是一把到位
5. 每一步都检查：
   - 是否接近关节限位
   - 是否速度过快
   - 是否出现异常接触
   - 手是否进入 `left_chest_front` 目标空间区域
6. 到达胸前区域后结束，并返回：
   - 实际关节变化
   - 实际末端位移
   - 最终姿态锚点
   - 是否成功达到目标区域

其中：

- 原语序列来自组合动作模板
- 每个原语的幅度来自录制得到的幅度表
- 实际执行中每一步仍然读当前状态

如果换成 `立腕`，则可以是更短的组合：

1. 进入允许起始锚点
2. 执行 `wrist_forward_up(small)` 或 `wrist_backward_up(small)`
3. 配合 `rotate_forearm_in/out(slight)` 做细调
4. 到达 `left_wrist_upright` 或 `right_wrist_upright` 区域后停止

## 13. 首期录制文件组织建议

建议录制数据不要只存成一个“无语义 episode 目录”，而是分资产类型保存。

例如：

```text
capx/assets/openarm/
  poses/
    home.v1.json
    left_pregrasp_high.v1.json
    handover_center.v1.json
  skills/
    pick_target/
      tomato.v1.yaml
      bottle.v1.yaml
    handover_transfer/
      default.v1.yaml
  datasets/
    2026-04-xx_pick_tomato_demo/
      episode_0001/
      episode_0002/
```

说明：

- `poses/` 是命名姿态资产
- `skills/` 是技能模板资产
- `datasets/` 是原始演示与回放数据

## 14. 当前建议的定稿版本

如果现在就拍板，我建议按下面版本推进：

1. 在线执行主路径使用“参数化技能 + 小步闭环”，不使用整段 episode 盲回放
2. 数据集回放只保留为调试、复现、标定工具
3. 首期对 LLM 暴露的 API 以 L1/L2 为主，L0 不暴露
4. 双臂动作先以“单臂抓取 + 双臂交接 + 双臂辅助稳定”三类为核心
5. 动作录制先重点做：
   - 命名姿态录制
   - 原语短轨迹录制
   - 完整任务录制
6. 录制结果拆成三类资产：
   - 原始时序数据
   - 技能模板资产
   - 技能元数据
7. `move_arm_joints_safe()` 保留，但只是辅助手段，不作为主任务执行接口

## 15. 下一步建议

在不改业务逻辑的前提下，下一步最值得继续细化的两件事是：

1. 把上面的 API 清单压缩成“首期最小可用版本 v1”
2. 逐个定义前 8 到 12 个核心技能的状态机、参数、守卫条件和失败恢复路径

只要这两步定下来，后面的实现就会非常顺。
