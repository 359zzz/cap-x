# import all environments here to register them!
from __future__ import annotations

from capx.envs.base import list_envs, register_env


def _safe_register(label: str, callback) -> None:
    del label
    try:
        callback()
    except Exception:
        pass


def _register_openarm() -> None:
    from .openarm_real import OpenArmRealLowLevel

    register_env("openarm_real_low_level", OpenArmRealLowLevel)


def _register_franka_real() -> None:
    from .franka_real import FrankaRealLowLevel

    register_env("franka_real_low_level", FrankaRealLowLevel)


def _register_robosuite() -> None:
    from .robosuite_cube_lift import FrankaRobosuiteCubeLiftLowLevel
    from .robosuite_cubes import FrankaRobosuiteCubesLowLevel
    from .robosuite_cubes_restack import FrankaRobosuiteCubesRestackLowLevel
    from .robosuite_handover import RobosuiteHandoverEnv
    from .robosuite_nut_assembly import FrankaRobosuiteNutAssembly
    from .robosuite_nut_assembly import FrankaRobosuiteNutAssemblyVisual
    from .robosuite_spill_wipe import FrankaRobosuiteSpillWipeLowLevel
    from .robosuite_two_arm_lift import RobosuiteTwoArmLiftEnv

    register_env("franka_robosuite_cube_lift_low_level", FrankaRobosuiteCubeLiftLowLevel)
    register_env("franka_robosuite_cubes_low_level", FrankaRobosuiteCubesLowLevel)
    register_env("franka_robosuite_cubes_restack_low_level", FrankaRobosuiteCubesRestackLowLevel)
    register_env("franka_robosuite_spill_wipe_low_level", FrankaRobosuiteSpillWipeLowLevel)
    register_env("franka_robosuite_nut_assembly_low_level", FrankaRobosuiteNutAssembly)
    register_env("franka_robosuite_nut_assembly_low_level_visual", FrankaRobosuiteNutAssemblyVisual)
    register_env("two_arm_handover_robosuite", RobosuiteHandoverEnv)
    register_env("two_arm_lift_robosuite", RobosuiteTwoArmLiftEnv)


def _register_libero() -> None:
    import functools

    from .libero import (
        FrankaLiberoOpenMicrowave,
        FrankaLiberoPickAlphabetSoup,
        FrankaLiberoPickPlace,
        FrankaLiberoTask,
    )

    register_env("franka_libero_pick_place_low_level", FrankaLiberoPickPlace)
    register_env("franka_libero_open_microwave_low_level", FrankaLiberoOpenMicrowave)
    register_env("franka_libero_pick_alphabet_soup_low_level", FrankaLiberoPickAlphabetSoup)

    for suite in ["libero_10", "libero_90", "libero_object", "libero_spatial", "libero_goal"]:
        try:
            from libero import benchmark as bm

            benchmark_dict = bm.get_benchmark_dict()
            task_count = benchmark_dict[suite]().n_tasks
        except Exception:
            task_count = 10
        for task_id in range(task_count):
            env_name = f"franka_libero_{suite}_{task_id}_low_level"
            register_env(
                env_name,
                functools.partial(FrankaLiberoTask, suite_name=suite, task_id=task_id),
            )


def _register_r1pro() -> None:
    from .r1pro_b1k import R1ProBehaviourLowLevel

    register_env("r1pro_b1k_low_level", R1ProBehaviourLowLevel)


_safe_register("OpenArm simulator", _register_openarm)
_safe_register("Franka real simulator", _register_franka_real)
_safe_register("Robosuite", _register_robosuite)
_safe_register("LIBERO", _register_libero)
_safe_register("R1Pro", _register_r1pro)


__all__ = ["list_envs"]
