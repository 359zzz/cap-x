from __future__ import annotations

from dataclasses import asdict, dataclass


JOINT_SEMANTICS: dict[str, dict[str, str]] = {
    "joint_1": {
        "description": "controls upper arm front/back",
        "motion_family": "raise_upper_arm/lower_upper_arm",
    },
    "joint_2": {
        "description": "controls upper arm open/close",
        "motion_family": "open_upper_arm/close_upper_arm",
    },
    "joint_3": {
        "description": "controls forearm rotation",
        "motion_family": "rotate_forearm_in/rotate_forearm_out",
    },
    "joint_4": {
        "description": "controls forearm lift/lower",
        "motion_family": "lift_forearm/lower_forearm",
    },
    "joint_5": {
        "description": "controls wrist rotation",
        "motion_family": "rotate_wrist_in/rotate_wrist_out",
    },
    "joint_6": {
        "description": "controls wrist side swing",
        "motion_family": "wrist_in/wrist_out",
    },
    "joint_7": {
        "description": "controls wrist open/close",
        "motion_family": "wrist_forward_up/wrist_backward_up",
    },
    "gripper": {
        "description": "controls gripper open/close",
        "motion_family": "open_gripper/close_gripper",
    },
}

DEFAULT_ANCHORS: list[str] = [
    "home",
    "safe_standby",
    "observe_front",
    "left_neutral_relaxed",
    "left_neutral_ready",
    "right_neutral_relaxed",
    "right_neutral_ready",
    "left_chest_front",
    "right_chest_front",
    "left_front_mid",
    "right_front_mid",
    "left_side_open",
    "right_side_open",
    "handover_center",
]

MAGNITUDE_TO_GRIPPER_FRACTION: dict[str, float] = {
    "slight": 0.10,
    "small": 0.25,
    "medium": 0.50,
    "large": 1.00,
}


@dataclass(frozen=True)
class MotionPrimitiveDefinition:
    name: str
    alias: str
    primary_joint_group: str
    spatial_semantics: str
    inverse_primitive: str
    allowed_start_anchors: list[str]
    direct_gripper_control: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MotionComboDefinition:
    name: str
    alias: str
    arm_mode: str
    spatial_semantics: str
    default_phases: list[dict[str, str]]
    allowed_start_anchors: list[str]
    goal_region: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_PRIMITIVES: dict[str, MotionPrimitiveDefinition] = {
    "raise_upper_arm": MotionPrimitiveDefinition(
        name="raise_upper_arm",
        alias="抬起大臂",
        primary_joint_group="upper_arm",
        spatial_semantics="Move the full arm forward and upward.",
        inverse_primitive="lower_upper_arm",
        allowed_start_anchors=["*_neutral_relaxed", "*_neutral_ready", "*_chest_front"],
    ),
    "lower_upper_arm": MotionPrimitiveDefinition(
        name="lower_upper_arm",
        alias="放下大臂",
        primary_joint_group="upper_arm",
        spatial_semantics="Move the full arm backward and downward.",
        inverse_primitive="raise_upper_arm",
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "*_side_open"],
    ),
    "open_upper_arm": MotionPrimitiveDefinition(
        name="open_upper_arm",
        alias="张开大臂",
        primary_joint_group="upper_arm",
        spatial_semantics="Open the upper arm away from the torso.",
        inverse_primitive="close_upper_arm",
        allowed_start_anchors=["*_neutral_relaxed", "*_neutral_ready", "*_chest_front"],
    ),
    "close_upper_arm": MotionPrimitiveDefinition(
        name="close_upper_arm",
        alias="内收大臂",
        primary_joint_group="upper_arm",
        spatial_semantics="Move the upper arm toward the body center line.",
        inverse_primitive="open_upper_arm",
        allowed_start_anchors=["*_neutral_ready", "*_side_open"],
    ),
    "lift_forearm": MotionPrimitiveDefinition(
        name="lift_forearm",
        alias="抬起小臂",
        primary_joint_group="forearm",
        spatial_semantics="Lift the forearm so the hand moves closer to the chest.",
        inverse_primitive="lower_forearm",
        allowed_start_anchors=["*_neutral_ready", "*_side_open", "*_front_mid"],
    ),
    "lower_forearm": MotionPrimitiveDefinition(
        name="lower_forearm",
        alias="放下小臂",
        primary_joint_group="forearm",
        spatial_semantics="Lower the forearm so the hand reaches further forward.",
        inverse_primitive="lift_forearm",
        allowed_start_anchors=["*_chest_front", "*_front_mid"],
    ),
    "rotate_forearm_in": MotionPrimitiveDefinition(
        name="rotate_forearm_in",
        alias="内旋小臂",
        primary_joint_group="forearm",
        spatial_semantics="Rotate the forearm inward toward the body.",
        inverse_primitive="rotate_forearm_out",
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "handover_center"],
    ),
    "rotate_forearm_out": MotionPrimitiveDefinition(
        name="rotate_forearm_out",
        alias="外旋小臂",
        primary_joint_group="forearm",
        spatial_semantics="Rotate the forearm outward away from the body.",
        inverse_primitive="rotate_forearm_in",
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "handover_center"],
    ),
    "rotate_wrist_in": MotionPrimitiveDefinition(
        name="rotate_wrist_in",
        alias="内旋手腕",
        primary_joint_group="wrist",
        spatial_semantics="Rotate the wrist inward along the forearm axis.",
        inverse_primitive="rotate_wrist_out",
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "handover_center"],
    ),
    "rotate_wrist_out": MotionPrimitiveDefinition(
        name="rotate_wrist_out",
        alias="外旋手腕",
        primary_joint_group="wrist",
        spatial_semantics="Rotate the wrist outward along the forearm axis.",
        inverse_primitive="rotate_wrist_in",
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "handover_center"],
    ),
    "wrist_in": MotionPrimitiveDefinition(
        name="wrist_in",
        alias="内收腕部",
        primary_joint_group="wrist",
        spatial_semantics="Swing the wrist toward the body center line.",
        inverse_primitive="wrist_out",
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "handover_center"],
    ),
    "wrist_out": MotionPrimitiveDefinition(
        name="wrist_out",
        alias="张开腕部",
        primary_joint_group="wrist",
        spatial_semantics="Swing the wrist away from the body center line.",
        inverse_primitive="wrist_in",
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "handover_center"],
    ),
    "wrist_forward_up": MotionPrimitiveDefinition(
        name="wrist_forward_up",
        alias="前抬腕部",
        primary_joint_group="wrist",
        spatial_semantics="Tilt the wrist forward and upward.",
        inverse_primitive="wrist_backward_up",
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "handover_center"],
    ),
    "wrist_backward_up": MotionPrimitiveDefinition(
        name="wrist_backward_up",
        alias="后抬腕部",
        primary_joint_group="wrist",
        spatial_semantics="Tilt the wrist backward and upward.",
        inverse_primitive="wrist_forward_up",
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "handover_center"],
    ),
    "open_gripper": MotionPrimitiveDefinition(
        name="open_gripper",
        alias="张开手爪",
        primary_joint_group="gripper",
        spatial_semantics="Open the gripper to create grasping space.",
        inverse_primitive="close_gripper",
        allowed_start_anchors=["*"],
        direct_gripper_control=True,
    ),
    "close_gripper": MotionPrimitiveDefinition(
        name="close_gripper",
        alias="收拢手爪",
        primary_joint_group="gripper",
        spatial_semantics="Close the gripper for holding or tactile contact.",
        inverse_primitive="open_gripper",
        allowed_start_anchors=["*"],
        direct_gripper_control=True,
    ),
}

DEFAULT_COMBOS: dict[str, MotionComboDefinition] = {
    "hand_to_chest": MotionComboDefinition(
        name="hand_to_chest",
        alias="举手到胸前",
        arm_mode="single",
        spatial_semantics="Move the selected hand to the chest-front region.",
        default_phases=[
            {"primitive": "raise_upper_arm", "magnitude": "small"},
            {"primitive": "lift_forearm", "magnitude": "medium"},
            {"primitive": "close_upper_arm", "magnitude": "slight"},
            {"primitive": "wrist_forward_up", "magnitude": "slight"},
        ],
        allowed_start_anchors=["*_neutral_relaxed", "*_neutral_ready"],
        goal_region="*_chest_front",
    ),
    "hand_forward_present": MotionComboDefinition(
        name="hand_forward_present",
        alias="向前递手",
        arm_mode="single",
        spatial_semantics="Extend the hand to the front-middle working region.",
        default_phases=[
            {"primitive": "raise_upper_arm", "magnitude": "small"},
            {"primitive": "lower_forearm", "magnitude": "small"},
            {"primitive": "wrist_forward_up", "magnitude": "slight"},
            {"primitive": "rotate_forearm_out", "magnitude": "slight"},
        ],
        allowed_start_anchors=["*_neutral_ready", "*_chest_front"],
        goal_region="*_front_mid",
    ),
    "wrist_upright": MotionComboDefinition(
        name="wrist_upright",
        alias="立腕",
        arm_mode="single",
        spatial_semantics="Adjust the wrist into an upright presentation pose.",
        default_phases=[
            {"primitive": "wrist_forward_up", "magnitude": "small"},
            {"primitive": "rotate_forearm_in", "magnitude": "slight"},
        ],
        allowed_start_anchors=["*_neutral_ready", "*_chest_front", "handover_center"],
        goal_region="*_wrist_upright",
    ),
    "wrist_inward_ready": MotionComboDefinition(
        name="wrist_inward_ready",
        alias="腕部内收预备",
        arm_mode="single",
        spatial_semantics="Rotate the wrist and forearm inward for close-to-body work.",
        default_phases=[
            {"primitive": "rotate_forearm_in", "magnitude": "small"},
            {"primitive": "wrist_in", "magnitude": "small"},
        ],
        allowed_start_anchors=["*_neutral_ready", "*_chest_front"],
        goal_region="*_wrist_inward_ready",
    ),
    "arm_half_open": MotionComboDefinition(
        name="arm_half_open",
        alias="半打开单臂",
        arm_mode="single",
        spatial_semantics="Open the arm halfway to create side-front working space.",
        default_phases=[
            {"primitive": "open_upper_arm", "magnitude": "medium"},
            {"primitive": "lower_forearm", "magnitude": "slight"},
        ],
        allowed_start_anchors=["*_neutral_relaxed", "*_neutral_ready"],
        goal_region="*_front_mid",
    ),
    "arm_full_open": MotionComboDefinition(
        name="arm_full_open",
        alias="全打开单臂",
        arm_mode="single",
        spatial_semantics="Open the arm widely to the side-open region.",
        default_phases=[
            {"primitive": "open_upper_arm", "magnitude": "large"},
            {"primitive": "lower_forearm", "magnitude": "small"},
            {"primitive": "wrist_out", "magnitude": "slight"},
        ],
        allowed_start_anchors=["*_neutral_relaxed", "*_neutral_ready"],
        goal_region="*_side_open",
    ),
    "both_arms_open": MotionComboDefinition(
        name="both_arms_open",
        alias="双臂打开",
        arm_mode="both",
        spatial_semantics="Open both arms outward to create a wider bimanual workspace.",
        default_phases=[
            {"primitive": "open_upper_arm", "magnitude": "large"},
            {"primitive": "lower_forearm", "magnitude": "small"},
            {"primitive": "wrist_out", "magnitude": "slight"},
        ],
        allowed_start_anchors=["left_neutral_ready+right_neutral_ready"],
        goal_region="left_side_open+right_side_open",
    ),
    "both_hands_to_chest": MotionComboDefinition(
        name="both_hands_to_chest",
        alias="双手收胸前",
        arm_mode="both",
        spatial_semantics="Bring both hands back to the chest-front regions.",
        default_phases=[
            {"primitive": "raise_upper_arm", "magnitude": "small"},
            {"primitive": "lift_forearm", "magnitude": "medium"},
            {"primitive": "close_upper_arm", "magnitude": "slight"},
            {"primitive": "wrist_forward_up", "magnitude": "slight"},
        ],
        allowed_start_anchors=["left_neutral_ready+right_neutral_ready"],
        goal_region="left_chest_front+right_chest_front",
    ),
    "handover_give_ready": MotionComboDefinition(
        name="handover_give_ready",
        alias="交接给出预备",
        arm_mode="single",
        spatial_semantics="Move one hand close to the center line for object handover.",
        default_phases=[
            {"primitive": "raise_upper_arm", "magnitude": "small"},
            {"primitive": "lift_forearm", "magnitude": "medium"},
            {"primitive": "wrist_forward_up", "magnitude": "slight"},
        ],
        allowed_start_anchors=["*_neutral_ready", "*_chest_front"],
        goal_region="handover_center",
    ),
    "handover_receive_ready": MotionComboDefinition(
        name="handover_receive_ready",
        alias="交接受理预备",
        arm_mode="single",
        spatial_semantics="Move one hand to the center line and open the gripper for receiving.",
        default_phases=[
            {"primitive": "raise_upper_arm", "magnitude": "small"},
            {"primitive": "lift_forearm", "magnitude": "medium"},
            {"primitive": "rotate_forearm_in", "magnitude": "small"},
            {"primitive": "wrist_in", "magnitude": "small"},
            {"primitive": "open_gripper", "magnitude": "large"},
        ],
        allowed_start_anchors=["*_neutral_ready", "*_chest_front"],
        goal_region="handover_center",
    ),
}


def primitive_catalog() -> list[dict[str, object]]:
    return [item.to_dict() for item in DEFAULT_PRIMITIVES.values()]


def combo_catalog() -> list[dict[str, object]]:
    return [item.to_dict() for item in DEFAULT_COMBOS.values()]
