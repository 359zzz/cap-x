# Cap-X OpenArm 动作词表 v1

## 1. 目标

本文档用于定下 `OpenArm` 双臂系统第一版动作词表。

这一版的原则是：

- 先定“解剖学原语”
- 再定“组合姿态”
- 暂不把 `pick_target()` 这类任务技能放进 v1 主词表
- 每个动作都必须有空间语义
- 每个动作都必须能落到可录制、可执行、可恢复的模板上

## 2. 统一约定

### 2.1 动作调用约定

建议 v1 先固定为以下接口：

- `execute_motion_primitive(arm, primitive, magnitude="medium", speed="normal")`
- `execute_bimanual_primitive(primitive, magnitude="medium", symmetry="mirror", speed="normal")`
- `execute_motion_combo(name, arm=None, magnitude="medium", speed="normal")`

参数约定：

- `arm`: `left` / `right`
- `magnitude`: `slight` / `small` / `medium` / `large`
- `speed`: `slow` / `normal`

### 2.2 锚点约定

v1 先固定这 14 个常用锚点：

| 锚点名 | 中文说明 |
| --- | --- |
| `home` | 全局回零姿态 |
| `safe_standby` | 安全待机姿态 |
| `observe_front` | 朝前观察姿态 |
| `left_neutral_relaxed` | 左臂自然放松中性位 |
| `left_neutral_ready` | 左臂待命中性位 |
| `right_neutral_relaxed` | 右臂自然放松中性位 |
| `right_neutral_ready` | 右臂待命中性位 |
| `left_chest_front` | 左侧胸前区域锚点 |
| `right_chest_front` | 右侧胸前区域锚点 |
| `left_front_mid` | 左臂身体前方中间工作区锚点 |
| `right_front_mid` | 右臂身体前方中间工作区锚点 |
| `left_side_open` | 左臂外展开区域锚点 |
| `right_side_open` | 右臂外展开区域锚点 |
| `handover_center` | 双臂中心交接区域锚点 |

### 2.3 关节语义映射约定

下面这张表以你的定义为准，作为本项目的 canonical 语义映射。

注意：

- 即使历史设计阶段参考过外部 `Evo-RL` 资料，`cap-x` 当前仓库实现也以这张映射表为准
- `gripper` 不是 `joint_7`
- `gripper` 必须直接暴露控制接口，因为后续要和你的触觉模块联动

| 关节 | 语义定义 | 对应动作家族 |
| --- | --- | --- |
| `joint_1` | 控制大臂前后 | `raise_upper_arm` / `lower_upper_arm` |
| `joint_2` | 控制大臂张开内收 | `open_upper_arm` / `close_upper_arm` |
| `joint_3` | 控制旋转小臂 | `rotate_forearm_in` / `rotate_forearm_out` |
| `joint_4` | 控制抬起/放下小臂 | `lift_forearm` / `lower_forearm` |
| `joint_5` | 控制旋转手腕 | `rotate_wrist_in` / `rotate_wrist_out` |
| `joint_6` | 控制腕部横摆 | `wrist_in` / `wrist_out` |
| `joint_7` | 控制腕部开合 | `wrist_forward_up` / `wrist_backward_up` |
| `gripper` | 控制夹爪张合 | `open_gripper` / `close_gripper` |

### 2.4 幅度解释约定

`magnitude` 不做全局统一角度，而是按动作家族标定。

| 幅度 | 语义 |
| --- | --- |
| `slight` | 轻微修正，用于姿态细调或组合动作最后收口 |
| `small` | 小幅动作，用于短距离切姿态 |
| `medium` | 常规动作，用于主流组合动作的默认档 |
| `large` | 明显动作，用于大范围姿态切换 |

## 3. v1 单动作原语表

v1 先定 16 个原语。

| primitive | 中文别名 | 主要影响部位 | 空间语义 | 允许起始锚点 | 逆动作 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| `raise_upper_arm` | 抬起大臂 | 肩部前抬 | 整条手臂向身体前上方抬起，手部通常向前上移动 | `*_neutral_relaxed`, `*_neutral_ready`, `*_chest_front` | `lower_upper_arm` | 主要用于把手送到更高、更靠前的工作区 |
| `lower_upper_arm` | 放下大臂 | 肩部回落 | 整条手臂向后下方回落，手部回到较低工作区 | `*_neutral_ready`, `*_chest_front`, `*_side_open` | `raise_upper_arm` | 常作为恢复动作 |
| `open_upper_arm` | 张开大臂 | 肩部外展 | 上臂向身体外侧张开，手部向侧前外侧移动 | `*_neutral_relaxed`, `*_neutral_ready`, `*_chest_front` | `close_upper_arm` | 用于腾空间、准备双臂协同 |
| `close_upper_arm` | 内收大臂 | 肩部内收 | 上臂向身体中线靠拢，手部更接近胸前和躯干前方 | `*_neutral_ready`, `*_side_open` | `open_upper_arm` | 和 `lift_forearm` 组合后常形成胸前姿态 |
| `lift_forearm` | 抬起小臂 | 肘部屈曲 | 小臂抬起，手更接近胸前或脸前区域 | `*_neutral_ready`, `*_side_open`, `*_front_mid` | `lower_forearm` | 适合形成展示、交接、胸前准备位 |
| `lower_forearm` | 放下小臂 | 肘部伸展 | 小臂向前下方伸展，手更远离身体 | `*_chest_front`, `*_front_mid` | `lift_forearm` | 常用于从胸前回到前伸位 |
| `rotate_forearm_in` | 内旋小臂 | 前臂旋转 | 前臂向身体内侧旋转，夹爪朝向更偏内侧 | `*_neutral_ready`, `*_chest_front`, `handover_center` | `rotate_forearm_out` | 常用于靠近身体、立腕微调 |
| `rotate_forearm_out` | 外旋小臂 | 前臂旋转 | 前臂向身体外侧旋转，夹爪朝向更偏外侧 | `*_neutral_ready`, `*_chest_front`, `handover_center` | `rotate_forearm_in` | 常用于外展和展示位 |
| `rotate_wrist_in` | 内旋手腕 | 手腕旋转 | 手腕绕前臂轴向内旋转，夹爪自身朝向发生旋转 | `*_neutral_ready`, `*_chest_front`, `handover_center` | `rotate_wrist_out` | 主要由 `joint_5` 驱动 |
| `rotate_wrist_out` | 外旋手腕 | 手腕旋转 | 手腕绕前臂轴向外旋转，夹爪自身朝向发生反向旋转 | `*_neutral_ready`, `*_chest_front`, `handover_center` | `rotate_wrist_in` | 主要由 `joint_5` 驱动 |
| `wrist_in` | 内收腕部 | 腕部横摆 | 腕部朝身体中线方向内收，手端更朝内侧 | `*_neutral_ready`, `*_chest_front`, `handover_center` | `wrist_out` | 适合靠近胸前或夹持前收口 |
| `wrist_out` | 张开腕部 | 腕部横摆 | 腕部朝身体外侧张开，手端更朝外侧 | `*_neutral_ready`, `*_chest_front`, `handover_center` | `wrist_in` | 适合展示或交接让位 |
| `wrist_forward_up` | 前抬腕部 | 腕部俯仰 | 手端朝前上方翘起，更接近“立腕” | `*_neutral_ready`, `*_chest_front`, `handover_center` | `wrist_backward_up` | 是 `wrist_upright` 组合的核心原语之一 |
| `wrist_backward_up` | 后抬腕部 | 腕部俯仰 | 手端朝后上方翘起，适合回退或反向立腕调整 | `*_neutral_ready`, `*_chest_front`, `handover_center` | `wrist_forward_up` | 和前臂旋转配合使用 |
| `open_gripper` | 张开手爪 | 夹爪 | 张开手爪，给抓取、接物、让渡留空间 | 任意稳定锚点 | `close_gripper` | 允许在大部分姿态下执行 |
| `close_gripper` | 收拢手爪 | 夹爪 | 收拢手爪，用于夹持、固定、接物 | 任意稳定锚点 | `open_gripper` | 后续可再细分力度档位 |

说明：

- 表中 `*_neutral_ready` 表示左右臂各自对应的 ready 锚点
- v1 暂不引入更多原语，先把这 16 个录好、调稳

## 4. v1 原语幅度表

下面给的是“标称建议值”，后续要按 `OpenArm` 实机做一次标定。

### 4.1 大臂类

| primitive | `slight` | `small` | `medium` | `large` | 末端空间效果 |
| --- | --- | --- | --- | --- | --- |
| `raise_upper_arm` | 4-6 deg | 8-12 deg | 15-22 deg | 28-35 deg | 手端向前上移动 |
| `lower_upper_arm` | 4-6 deg | 8-12 deg | 15-22 deg | 28-35 deg | 手端向后下回落 |
| `open_upper_arm` | 4-6 deg | 8-10 deg | 14-18 deg | 22-28 deg | 手端向侧外侧移动 |
| `close_upper_arm` | 4-6 deg | 8-10 deg | 14-18 deg | 22-28 deg | 手端向胸前靠近 |

### 4.2 小臂类

| primitive | `slight` | `small` | `medium` | `large` | 末端空间效果 |
| --- | --- | --- | --- | --- | --- |
| `lift_forearm` | 5-8 deg | 10-15 deg | 18-26 deg | 30-40 deg | 手更靠近胸前、更高 |
| `lower_forearm` | 5-8 deg | 10-15 deg | 18-26 deg | 30-40 deg | 手更远离身体、更低 |
| `rotate_forearm_in` | 5-8 deg | 10-15 deg | 18-24 deg | 28-35 deg | 夹爪朝向更偏内侧 |
| `rotate_forearm_out` | 5-8 deg | 10-15 deg | 18-24 deg | 28-35 deg | 夹爪朝向更偏外侧 |

### 4.3 手腕旋转类

| primitive | `slight` | `small` | `medium` | `large` | 末端空间效果 |
| --- | --- | --- | --- | --- | --- |
| `rotate_wrist_in` | 4-6 deg | 8-10 deg | 12-18 deg | 20-28 deg | 夹爪自身朝向绕前臂轴向内旋 |
| `rotate_wrist_out` | 4-6 deg | 8-10 deg | 12-18 deg | 20-28 deg | 夹爪自身朝向绕前臂轴向外旋 |

### 4.4 腕部摆动 / 开合类

| primitive | `slight` | `small` | `medium` | `large` | 末端空间效果 |
| --- | --- | --- | --- | --- | --- |
| `wrist_in` | 4-6 deg | 8-10 deg | 12-16 deg | 18-24 deg | 手端朝身体内侧偏转 |
| `wrist_out` | 4-6 deg | 8-10 deg | 12-16 deg | 18-24 deg | 手端朝身体外侧偏转 |
| `wrist_forward_up` | 4-6 deg | 8-10 deg | 12-16 deg | 18-24 deg | 手端朝前上方翘起 |
| `wrist_backward_up` | 4-6 deg | 8-10 deg | 12-16 deg | 18-24 deg | 手端朝后上方翘起 |

### 4.5 夹爪类

| primitive | `slight` | `small` | `medium` | `large` | 说明 |
| --- | --- | --- | --- | --- | --- |
| `open_gripper` | 10% 行程 | 25% 行程 | 50% 行程 | 100% 行程 | v1 可先直接把 `large` 视为 fully open |
| `close_gripper` | 10% 行程 | 25% 行程 | 50% 行程 | 100% 行程 | 真正抓取时还应加触觉/电流闭环 |

## 5. v1 组合动作表

v1 先定 10 个组合动作。

| combo | 中文别名 | 适用侧 | 空间语义 | 默认原语序列 | 允许起始锚点 | 结束目标 |
| --- | --- | --- | --- | --- | --- | --- |
| `hand_to_chest` | 举手到胸前 | `left/right` | 将指定侧手部移动到身体前方胸口区域 | `raise_upper_arm(small)` -> `lift_forearm(medium)` -> `close_upper_arm(slight)` -> `wrist_forward_up(slight)` | `*_neutral_relaxed`, `*_neutral_ready` | `*_chest_front` |
| `hand_forward_present` | 向前递手 | `left/right` | 将手向身体正前方递出，适合展示、递物、试探接近 | `raise_upper_arm(small)` -> `lower_forearm(small)` -> `wrist_forward_up(slight)` -> `rotate_forearm_out(slight)` | `*_neutral_ready`, `*_chest_front` | `*_front_mid` |
| `wrist_upright` | 立腕 | `left/right` | 将腕部调整到较接近竖直、便于接物或展示的姿态 | `wrist_forward_up(small)` -> `rotate_forearm_in(slight)` 或 `rotate_forearm_out(slight)` | `*_neutral_ready`, `*_chest_front`, `handover_center` | `*_wrist_upright` 语义区域 |
| `wrist_inward_ready` | 腕部内收预备 | `left/right` | 将腕部和前臂调整到更适合向身体内侧操作的姿态 | `rotate_forearm_in(small)` -> `wrist_in(small)` | `*_neutral_ready`, `*_chest_front` | `*_wrist_inward_ready` 语义区域 |
| `arm_half_open` | 半打开单臂 | `left/right` | 单臂向身体侧前方半打开，给前方和中侧方留操作空间 | `open_upper_arm(medium)` -> `lower_forearm(slight)` | `*_neutral_relaxed`, `*_neutral_ready` | 侧前方中间工作区 |
| `arm_full_open` | 全打开单臂 | `left/right` | 单臂明显向身体外侧张开，形成大幅外展姿态 | `open_upper_arm(large)` -> `lower_forearm(small)` -> `wrist_out(slight)` | `*_neutral_relaxed`, `*_neutral_ready` | `*_side_open` |
| `both_arms_open` | 双臂打开 | `both` | 双臂同时外展，形成更开阔的双臂工作空间 | 左右臂同时执行 `arm_full_open` 镜像版 | `left_neutral_ready` + `right_neutral_ready` | 左右各到 `*_side_open` |
| `both_hands_to_chest` | 双手收胸前 | `both` | 双手同时收到胸前区域，适合准备接物、展示或同步动作 | 左右臂同时执行 `hand_to_chest` 镜像版 | 双臂 ready / relaxed | 左右各到 `*_chest_front` |
| `handover_give_ready` | 交接给出预备 | `left/right` | 指定侧手部进入靠近中心线的给出姿态 | `hand_to_chest` -> `open_upper_arm(slight)` 或 `close_upper_arm(slight)` 视左右侧而定 -> `wrist_upright` | `*_neutral_ready`, `*_chest_front` | `handover_center` 附近给出区 |
| `handover_receive_ready` | 交接受理预备 | `left/right` | 指定侧手部进入中心线附近的接收姿态，给另一只手留接近空间 | `hand_to_chest` -> `wrist_inward_ready` -> `open_gripper(large)` | `*_neutral_ready`, `*_chest_front` | `handover_center` 附近接收区 |

说明：

- 表中的 `wrist_upright` 既是组合动作名，也可以被其他组合动作复用
- 组合动作之间允许复用，但执行前必须全部展开成原语序列

## 6. v1 录制表

录制建议按三批走，不要一上来录完整任务。

### 6.1 第一批：锚点录制

先录这 14 个：

- `home`
- `safe_standby`
- `observe_front`
- `left_neutral_relaxed`
- `left_neutral_ready`
- `right_neutral_relaxed`
- `right_neutral_ready`
- `left_chest_front`
- `right_chest_front`
- `left_front_mid`
- `right_front_mid`
- `left_side_open`
- `right_side_open`
- `handover_center`

### 6.2 第二批：原语幅度录制

优先录这 12 个主力原语：

- `raise_upper_arm`
- `lower_upper_arm`
- `open_upper_arm`
- `close_upper_arm`
- `lift_forearm`
- `lower_forearm`
- `rotate_forearm_in`
- `rotate_forearm_out`
- `rotate_wrist_in`
- `rotate_wrist_out`
- `wrist_forward_up`
- `wrist_in`

录制规则：

- 每个原语至少从 `*_neutral_ready` 录一套四档
- 对最常用原语，再从 `*_chest_front` 补一套四档
- 每条原语轨迹都保存：
  - 起始锚点
  - 关节增量
  - 末端位移估计
  - 推荐速度
  - 触碰守卫阈值

### 6.3 第三批：组合动作录制

先录这 6 个：

- `hand_to_chest`
- `wrist_upright`
- `wrist_inward_ready`
- `arm_half_open`
- `both_arms_open`
- `handover_receive_ready`

录制规则：

- 组合动作不是只存一条大轨迹
- 要同时存：
  - 原语序列
  - 中间检查点
  - 完成区域
  - 失败恢复姿态

## 7. v1 执行规则

### 7.1 原语执行

`execute_motion_primitive()` 的推荐执行流程：

1. 判断当前是否处于允许起始锚点附近。
2. 如果不在，则先切到最近的允许锚点。
3. 读取该原语在该锚点下、对应 `magnitude` 的模板。
4. 将该模板拆成 3 到 6 个小步。
5. 每一步执行前后检查：
   - 关节限位
   - 速度限幅
   - 异常触碰
   - 偏离目标趋势是否过大
6. 完成后返回：
   - 实际关节变化
   - 实际末端位移
   - 最终落点区域

### 7.2 组合动作执行

`execute_motion_combo()` 的推荐执行流程：

1. 展开组合动作对应的原语序列。
2. 在每两个原语之间插入检查点。
3. 如果中途偏差太大，则回退到最近恢复锚点。
4. 全部完成后，检查末端是否进入目标区域。
5. 返回结构化结果：
   - `success`
   - `final_anchor`
   - `final_region`
   - `executed_primitives`
   - `safety_events`

### 7.3 为什么不用“整段回放”做主路径

因为这张表的核心不是“任务轨迹”，而是“动作词汇”。

对于动作词汇体系：

- 原语执行更适合“模板增量 + 小步闭环”
- 组合动作更适合“原语展开 + 检查点”
- 整段回放只适合做：
  - 标定参考
  - 录制回看
  - 演示复现

## 8. v1 定稿建议

如果现在就拍板，我建议按下面版本推进：

1. 原语固定为 14 个，不再继续扩词。
2. 组合动作固定为 10 个，优先胸前、立腕、打开、交接准备这几类。
3. `magnitude` 固定四档，不再改名。
4. 先录锚点，再录原语幅度，再录组合动作。
5. 录制资产主用于在线执行模板，不主用于整段回放。
6. 第二阶段再把面向物体的 `approach_target()`、`pick_target()` 叠上来。

## 9. v1 资产层下压

这一节把动作词表再下压一层，直接对应到后续录制文件和执行器读取字段。

### 9.1 原语模板资产命名规则

建议每个原语模板都按“单臂、单起始锚点、单档幅度”独立存储。

推荐 `asset_id` 规则：

```text
primitive.<arm>.<start_anchor>.<primitive>.<magnitude>.v1
```

例如：

```text
primitive.left.left_neutral_ready.raise_upper_arm.medium.v1
primitive.right.right_chest_front.rotate_forearm_in.small.v1
```

推荐目录：

```text
capx/assets/openarm/primitives/
  raise_upper_arm/
    left.left_neutral_ready.slight.v1.yaml
    left.left_neutral_ready.small.v1.yaml
    left.left_neutral_ready.medium.v1.yaml
    left.left_neutral_ready.large.v1.yaml
  rotate_forearm_in/
    right.right_chest_front.small.v1.yaml
```

### 9.2 原语模板必存字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `str` | 资产唯一标识 |
| `version` | `str` | 例如 `v1` |
| `arm` | `str` | `left` / `right` |
| `primitive` | `str` | 原语名 |
| `magnitude` | `str` | 四档之一 |
| `start_anchor` | `str` | 录制时的起始锚点 |
| `allowed_start_anchors` | `list[str]` | 允许运行时从哪些锚点复用该模板 |
| `primary_joint_group` | `str` | 如 `upper_arm` / `forearm` / `wrist` / `gripper` |
| `nominal_joint_delta_deg` | `dict[str, float]` | 各关节标称增量，单位度 |
| `joint_delta_tolerance_deg` | `dict[str, float]` | 执行后允许偏差 |
| `nominal_ee_delta_base` | `list[float]` | 基坐标系下末端标称位移提示 |
| `nominal_ee_delta_local` | `list[float]` | 局部坐标系下末端标称位移提示 |
| `end_region_hint` | `str` | 预期结束区域，例如 `left_chest_front` |
| `default_step_count` | `int` | 建议拆分步数，通常 3 到 6 |
| `default_speed` | `str` | `slow` / `normal` |
| `settle_time_ms` | `int` | 每步后稳定等待时间 |
| `timeout_ms` | `int` | 整个原语执行超时 |
| `guard_joint_margin_deg` | `float` | 关节距限位的最小余量 |
| `guard_max_step_delta_deg` | `float` | 单步最大关节改变量 |
| `guard_max_ee_error_m` | `float` | 允许的末端偏差 |
| `guard_abort_on_tactile_contact` | `bool` | 是否遇接触即停 |
| `guard_abort_on_torque_spike` | `bool` | 是否遇扭矩异常即停 |
| `inverse_primitive` | `str` | 逆动作名 |
| `recovery_anchor` | `str` | 失败回退目标锚点 |
| `source_recording_id` | `str` | 来源录制编号 |
| `operator` | `str` | 录制操作者 |
| `notes` | `str` | 补充说明 |

说明：

- `nominal_joint_delta_deg` 是执行器真正最依赖的字段
- `nominal_ee_delta_*` 是给 LLM 文档、日志和后续调参用的
- v1 先不要求每个模板都包含完整动力学信息

### 9.3 组合动作模板命名规则

推荐 `asset_id` 规则：

```text
combo.<arm_mode>.<combo_name>.<magnitude>.v1
```

例如：

```text
combo.single.hand_to_chest.medium.v1
combo.both.both_arms_open.medium.v1
```

推荐目录：

```text
capx/assets/openarm/combos/
  hand_to_chest/
    single.medium.v1.yaml
  both_arms_open/
    both.medium.v1.yaml
```

### 9.4 组合动作模板必存字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `str` | 组合动作资产唯一标识 |
| `version` | `str` | 例如 `v1` |
| `combo` | `str` | 组合动作名 |
| `arm_mode` | `str` | `single` / `both` |
| `allowed_start_anchors` | `list[str]` | 组合动作允许从哪些锚点开始 |
| `goal_region` | `str` | 预期最终区域 |
| `goal_pose_anchor` | `str | null` | 如有固定目标姿态则填写 |
| `default_speed` | `str` | 默认速度档 |
| `phases` | `list[dict]` | 原语阶段列表 |
| `phase_checkpoints` | `list[dict]` | 相邻阶段之间的检查点 |
| `completion_rule` | `dict` | 判定动作完成的规则 |
| `abort_rule` | `dict` | 判定动作中止的规则 |
| `recovery_anchor` | `str` | 失败回退锚点 |
| `source_recording_ids` | `list[str]` | 来源录制编号 |

其中 `phases` 里的每一项建议至少包含：

- `primitive`
- `magnitude`
- `arm`
- `expected_region_after_phase`
- `settle_time_ms`
- `abort_on_contact`
- `allow_skip_if_already_in_region`

### 9.5 原语录制作业单元表

这一层用于指导录制人员按什么顺序、从哪些锚点录。

| primitive | 先录哪只臂 | 先录起始锚点 | 必录幅度 | 每档最少录制次数 | 通过判据 |
| --- | --- | --- | --- | --- | --- |
| `raise_upper_arm` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 手端明显向前上移动，且无异常触碰 |
| `lower_upper_arm` | `left` 后 `right` | `*_chest_front` | 四档全录 | 3 次 | 手端明显向后下回落，且回退稳定 |
| `open_upper_arm` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 手端朝外侧展开，末端远离身体中线 |
| `close_upper_arm` | `left` 后 `right` | `*_side_open` | 四档全录 | 3 次 | 手端回到更靠胸前的区域 |
| `lift_forearm` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 肘部抬起，手更靠近胸前 |
| `lower_forearm` | `left` 后 `right` | `*_chest_front` | 四档全录 | 3 次 | 肘部展开，手更远离身体 |
| `rotate_forearm_in` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 夹爪朝内侧偏转，臂形稳定 |
| `rotate_forearm_out` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 夹爪朝外侧偏转，臂形稳定 |
| `rotate_wrist_in` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 手腕自身旋转稳定，夹爪朝向明显变化 |
| `rotate_wrist_out` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 手腕自身反向旋转稳定，夹爪朝向明显变化 |
| `wrist_in` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 腕部朝内侧偏转，末端无抖动 |
| `wrist_out` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 腕部朝外侧偏转，末端无抖动 |
| `wrist_forward_up` | `left` 后 `right` | `*_neutral_ready` | 四档全录 | 3 次 | 手端朝前上方翘起 |
| `wrist_backward_up` | `left` 后 `right` | `*_chest_front` | `slight/small/medium` 先录 | 3 次 | 手端朝后上方翘起且不撞臂 |
| `open_gripper` | 双侧都录 | 常用稳定锚点 | 四档全录 | 2 次 | 开度达到目标行程 |
| `close_gripper` | 双侧都录 | 常用稳定锚点 | 四档全录 | 2 次 | 闭合达到目标行程或安全触碰阈值 |

### 9.6 组合动作录制作业单元表

| combo | 录制模式 | 每个侧最少录制次数 | 必录中间检查点 | 完成判据 |
| --- | --- | --- | --- | --- |
| `hand_to_chest` | 单臂组合录制 | 3 次 | `front_mid` 过渡区 | 手进入 `*_chest_front` |
| `hand_forward_present` | 单臂组合录制 | 3 次 | 手离开胸前、进入前方中区 | 手进入 `*_front_mid` |
| `wrist_upright` | 单臂短组合录制 | 3 次 | 腕部角度检查点 | 达到 `*_wrist_upright` 语义区 |
| `wrist_inward_ready` | 单臂短组合录制 | 3 次 | 前臂内旋检查点 | 达到 `*_wrist_inward_ready` 语义区 |
| `arm_half_open` | 单臂组合录制 | 3 次 | 大臂外展检查点 | 手到侧前中间区 |
| `arm_full_open` | 单臂组合录制 | 3 次 | 大臂外展 + 腕部外摆 | 手到 `*_side_open` |
| `both_arms_open` | 双臂同步录制 | 3 次 | 左右对称检查点 | 左右都到 `*_side_open` |
| `both_hands_to_chest` | 双臂同步录制 | 3 次 | 左右胸前检查点 | 左右都到 `*_chest_front` |
| `handover_give_ready` | 单臂组合录制 | 3 次 | 接近中心线检查点 | 手进入 `handover_center` 给出区 |
| `handover_receive_ready` | 单臂组合录制 | 3 次 | 接近中心线 + 张爪检查点 | 手进入 `handover_center` 接收区 |

### 9.7 执行器返回结构建议

为了便于 `cap-x` 多轮生成和 `web-ui` 展示，建议每次动作执行都返回结构化结果。

原语执行建议返回：

```json
{
  "success": true,
  "arm": "left",
  "primitive": "raise_upper_arm",
  "magnitude": "medium",
  "start_anchor": "left_neutral_ready",
  "final_region": "left_front_mid",
  "executed_steps": 4,
  "joint_delta_deg": {"joint_x": 18.0},
  "ee_delta_base": [0.10, 0.01, 0.08],
  "safety_events": [],
  "recovery_used": false
}
```

组合动作建议返回：

```json
{
  "success": true,
  "combo": "hand_to_chest",
  "arm": "left",
  "magnitude": "medium",
  "start_anchor": "left_neutral_ready",
  "final_region": "left_chest_front",
  "executed_primitives": [
    "raise_upper_arm",
    "lift_forearm",
    "close_upper_arm",
    "wrist_forward_up"
  ],
  "checkpoint_results": [],
  "safety_events": [],
  "recovery_used": false
}
```

## 10. 开始编码前的已确认项与剩余非阻塞项

### 10.1 你已确认的 5 项

下面 5 件现在都已经拍板，可以作为编码默认值：

1. 关节语义映射：
   - `joint_1` 大臂前后
   - `joint_2` 大臂张开内收
   - `joint_3` 旋转小臂
   - `joint_4` 抬起/放下小臂
   - `joint_5` 旋转手腕
   - `joint_6` 腕部横摆
   - `joint_7` 腕部开合
   - `gripper` 独立直接暴露
2. 录制主方式：
   - 先用手动方式
3. 感知接入策略：
   - 首期先用内部 adapter 兼容现有模块
4. 第一编码阶段范围：
   - 先不包含 `nanobot` App 整合
5. 触觉掉线默认策略：
   - 采用当前约定的保守降级策略

### 10.2 现在已经没有硬 blocker

按当前信息，已经可以正式开始第一阶段编码。

第一阶段我可以直接做：

- `OpenArmRuntime`
- `OpenArmMotionAssetRegistry`
- `OpenArmMotionExecutor`
- `OpenArmControlApi` 的动作词表接口
- 手动锚点录制器
- 手动 jog 原语录制器
- 单活跃任务锁
- `web-ui` 执行日志

### 10.3 剩余非阻塞项

这些不影响我开始编码，我可以先按保守默认值实现：

- 各原语四档幅度的精确角度
- 每步 `settle_time_ms`
- `guard_joint_margin_deg`
- `guard_max_step_delta_deg`
- 夹爪四档开合的精确行程
- `combo` 名字是否还要微调
- 哪些组合动作进入 `v1.1`
- 第一阶段代码里先重点打通左臂还是双臂同时打通

### 10.4 建议的默认实现顺序

为了又快又稳，我建议：

1. 代码结构一开始就按双臂设计
2. 调试顺序先左臂，再镜像到右臂
3. 先打通锚点录制
4. 再打通单原语执行与录制
5. 最后再叠组合动作

## 11. v1 再下压一层：实现落点 / 录制命令 / 执行主路径

这一节把动作词表和当前代码落点直接对应起来，避免后面“表是一套、代码是一套、文档又是一套”。

### 11.1 代码落点映射

| 层 | 当前代码文件 | 责任 |
| --- | --- | --- |
| 动作语义总表 | `capx/integrations/openarm/catalog.py` | 维护关节语义、原语表、组合动作表、默认锚点 |
| 资产 schema | `capx/integrations/openarm/assets.py` | 定义 anchor / primitive / combo 资产格式与读写规则 |
| 实机运行时 | `capx/integrations/openarm/runtime.py` | 对接仓库内嵌的双臂 OpenArm driver，执行保守关节步进与夹爪控制 |
| 原语 / 组合执行器 | `capx/integrations/openarm/executor.py` | 做“找锚点 -> 选模板 -> 小步执行 -> 返回结构化结果” |
| LLM 可调用接口 | `capx/integrations/openarm/control.py` | 暴露 `execute_motion_primitive` / `execute_motion_combo` / `open_gripper` 等函数 |
| 手动录制器 | `capx/integrations/openarm/recording.py` | 录锚点、录原语模板、生成组合动作模板 |
| 录制 CLI | `capx/cli/openarm_assets.py` | 把录制器能力变成直接可执行命令 |
| 实机 low-level env | `capx/envs/simulators/openarm_real.py` | 把 OpenArm runtime 封装成 `cap-x` low-level env |
| 代码生成 env | `capx/envs/tasks/openarm/openarm_motion.py` | 给 LLM 提供 OpenArm 执行环境与 prompt |
| web-ui / nanobot relay | `capx/web/server.py`, `capx/web/nanobot_relay.py`, `capx/cli/nanobot_task.py` | 让外部壳层通过任务接口驱动 OpenArm |
| 内嵌 nanobot shell | `capx/nanobot/robot_shell.py`, `capx/nanobot/task_client.py`, `capx/cli/nanobot_console.py` | 在 repo 内提供第一版消息壳，用自然语言驱动 start/status/inject/stop |
| 内嵌 nanobot gateway | `capx/nanobot/channels/*`, `capx/nanobot/runtime.py`, `capx/nanobot/gateway_app.py`, `capx/cli/nanobot_gateway.py`, `capx/cli/nanobot_http_gateway.py` | 已提供 console channel、HTTP bridge channel、gateway runtime 与 app 侧 HTTP 网关入口 |
| 部署自检 | `capx/cli/openarm_doctor.py` | 检查内置 driver、`python-can`、端口、资产、感知服务、relay 与可选实机连通性 |
| 实机默认配置 | `env_configs/openarm/openarm_motion_real.yaml` | CPU / 实机 / web-ui 的默认入口配置 |

### 11.2 原语模板和组合模板的实际落盘位置

这一层对应当前 asset registry 的真实目录行为。

| 资产类型 | 目录 | 文件命名规则 |
| --- | --- | --- |
| anchor | `capx/assets/openarm/anchors/` | `<anchor_name>.v1.yaml` |
| primitive template | `capx/assets/openarm/primitives/<primitive>/` | `<arm>.<start_anchor>.<magnitude>.v1.yaml` |
| combo template | `capx/assets/openarm/combos/<combo>/` | `<arm_mode>.<magnitude>.v1.yaml` |

例子：

```text
capx/assets/openarm/anchors/left_neutral_ready.v1.yaml
capx/assets/openarm/primitives/raise_upper_arm/left.left_neutral_ready.medium.v1.yaml
capx/assets/openarm/combos/hand_to_chest/single.medium.v1.yaml
```

### 11.3 录制命令映射

这一层把“录什么”对应成“怎么录”。

#### A. 锚点录制

适用于：

- `home`
- `safe_standby`
- `left_neutral_ready`
- `right_neutral_ready`
- `left_chest_front`
- `right_chest_front`

命令模式：

```bash
python -m capx.cli.openarm_assets record-anchor <anchor_name> --arm-mode single --arm left
python -m capx.cli.openarm_assets record-anchor <anchor_name> --arm-mode single --arm right
python -m capx.cli.openarm_assets record-anchor <anchor_name> --arm-mode both
```

#### B. 原语模板录制

适用于：

- `raise_upper_arm`
- `open_upper_arm`
- `lift_forearm`
- `rotate_forearm_in`
- `rotate_wrist_out`
- `wrist_in`
- `open_gripper`

命令模式：

```bash
python -m capx.cli.openarm_assets record-primitive <arm> <primitive> <magnitude> <start_anchor> --end-region-hint <region>
```

例如：

```bash
python -m capx.cli.openarm_assets record-primitive left raise_upper_arm medium left_neutral_ready --end-region-hint left_front_mid
```

#### C. 组合动作模板生成 / 修订

命令模式：

```bash
python -m capx.cli.openarm_assets bootstrap-combos --overwrite
python -m capx.cli.openarm_assets record-combo <combo> --arm-mode single --magnitude medium
python -m capx.cli.openarm_assets record-combo <combo> --arm-mode both --magnitude medium
```

说明：

- `bootstrap-combos` 先生成一套可编辑初稿
- `record-combo` 当前阶段主要是把组合动作的 phase/recovery 结构固化下来
- v1 不是把组合动作录成一条整轨迹直接回放

### 11.4 录制到执行的最终主路径

这一层是这套系统最关键的定稿。

#### 原语主路径

1. 人工先录 anchor。
2. 人工把手臂放到 `start_anchor`。
3. 人工把手臂推到目标姿态后执行 `record-primitive`。
4. 系统保存的是“相对起始锚点的关节增量模板”。
5. 运行时执行器根据当前关节状态选择最近允许锚点。
6. 如有必要先回该锚点。
7. 再按模板的小步增量去执行。

结论：

- 原语资产的本质是“增量模板”
- 不是“整段轨迹回放文件”

#### 组合动作主路径

1. 组合动作模板先保存为一串 phase。
2. 每个 phase 指向一个原语和一个幅度。
3. 执行时展开成多个原语调用。
4. 每个原语之间可以插入检查点。
5. 如失败则回 `recovery_anchor`。

结论：

- 组合动作资产的本质是“原语编排模板”
- 不是“长轨迹示教回放”

### 11.5 “回放录制的数据集吗” 的当前结论

当前结论已经明确：

1. v1 不以“整段数据集回放”作为主要执行方式。
2. v1 的主执行方式是：
   - 锚点对齐
   - 原语增量模板
   - 小步闭环执行
   - 组合动作展开
3. 如后续要引入整段轨迹录制，它的角色更适合：
   - 演示复现
   - 标定对比
   - 离线分析
   - 生成更好的原语模板初值

也就是说：

- 录制资产服务于“可解释动作词汇执行”
- 而不是让机器人主要靠“回放一段长示教”

### 11.6 现在开始继续编码还剩什么未决定项

到当前这一版，已经没有架构级 blocker。

还剩下的都是部署 / 标定级非阻塞项：

- 左右臂真实端口和 CAN 参数最终值
- `calibration_dir` 是否需要单独指定
- 第一批 anchor 的实机标定值
- 第一批原语四档的实机最终幅度
- 感知服务里哪些检测标签要作为默认词汇
- nanobot 外部 app/channel 代码何时一起 vendoring 进 repo

这些都不影响继续落第一阶段代码，因为当前代码骨架已经可以先用保守默认值跑通。

### 11.7 结合当前代码后的剩余实现清单

截至 `2026-04-09`，已经落地的部分有：

1. OpenArm runtime / executor / asset registry / recording CLI
2. `cap-x` OpenArm 实机 env 与默认 YAML
3. `cap-x` web-ui 下的 nanobot relay
4. repo 内嵌的 nanobot shell
5. repo 内嵌的 nanobot channel manager / console channel / HTTP bridge channel / gateway app
6. OpenArm 面向物体的第一批高层动作：
   - `get_tactile_health()`
   - `estimate_arm_region()`
   - `align_to_target()`
   - `approach_target()`
   - `descend_until_contact()`
   - `grasp_with_tactile_guard()`
   - `release_grasp()`
   - `handover_to_center()`
7. `openarm_doctor` 部署自检命令

现在还剩下、但后面继续做会更有价值的代码主要有 5 类：

#### A. 真实 app 协议适配

当前状态：

- 已有通用 HTTP bridge channel
- app 只需要对接 `/channels/http/inbound` 和 `/channels/http/outbound`

剩余代码：

- 接你真正使用的 app SDK / 协议
- app 用户身份、会话映射、回复消息 ID 关联
- 断线重连、鉴权、消息去重

#### B. OpenArm 感知与触觉联动深化

当前状态：

- 已有 perception adapter
- 已有高层目标接近 / 接触 / 夹持接口

剩余代码：

- 触觉阈值按你的真实传感器重新标定
- 抓取稳定判据与松手判据细化
- 更细的目标检测结构化语义

#### C. 录制资产到实机标定数据

当前状态：

- 录制代码和落盘结构已在
- 真正决定动作质量的仍然是你后续录入的 anchor / primitive / combo 资产

剩余代码：

- 第一批 anchor 实机录制
- 第一批原语四档录制
- 第一批组合动作 phase / checkpoint 实机修订

#### D. 更深的守卫与恢复策略

当前状态：

- 组合动作已有 checkpoint、abort、completion、recovery 的基础框架

剩余代码：

- phase checkpoint 更细地参与运行时决策
- `abort_rule` / `completion_rule` 的规则继续加严
- `recovery_anchor` 的分级回退逻辑继续细化

#### E. 启停编排与高级规划

当前状态：

- 已有 doctor、gateway、web-ui、relay 和手工命令

剩余代码：

- OpenArm / perception / relay 一键启动脚本
- 配置合法性检查进一步前置
- 更复杂的物体级规划与双臂协同策略
