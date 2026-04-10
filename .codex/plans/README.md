# OpenArm / Nanobot Plans Index

This page is the public entry point for the design and planning notes that were created while integrating:

- `OpenArm` dual-arm real-robot control
- `Evo-RL` low-level driver reuse
- `openclaw_realsense_agent` perception and tactile reuse
- embedded `nanobot`-style shell, relay, and HTTP app gateway inside `cap-x`

These documents are design notes, implementation plans, and execution records for the OpenArm-specific path. They complement, but do not replace, the runnable usage guide in [docs/openarm-nanobot.md](../../docs/openarm-nanobot.md).

## Recommended Reading Order

If you want the shortest path to understanding the whole stack, read in this order:

1. [docs/openarm-nanobot.md](../../docs/openarm-nanobot.md)
   Use this first if your goal is to bring the system up or run commands on a real machine.
2. [capx-openarm-motion-v1-table.md](./capx-openarm-motion-v1-table.md)
   This is the most complete motion-vocabulary and asset-design document.
3. [capx-openarm-control-api-skill-recording-plan.md](./capx-openarm-control-api-skill-recording-plan.md)
   Read this next if you care about API boundaries, action recording, and execution structure.
4. [capx-nanobot-robot-arch-plan.md](./capx-nanobot-robot-arch-plan.md)
   This explains how the embedded nanobot shell and relay were intended to fit into `cap-x`.
5. [capx-nanobot-openarm-detailed-architecture.md](./capx-nanobot-openarm-detailed-architecture.md)
   Read this for the most detailed end-to-end architecture breakdown.

## Document Map

### 1. Motion Vocabulary and Assets

- [capx-openarm-motion-v1-table.md](./capx-openarm-motion-v1-table.md)
  Defines the OpenArm primitive/combo vocabulary, joint semantics, asset layout, recording flow, and execution expectations.

### 2. API, Recording, and Skill Surface

- [capx-openarm-control-api-skill-recording-plan.md](./capx-openarm-control-api-skill-recording-plan.md)
  Covers the `OpenArmControlApi` surface, action recording direction, and how higher-level callable robot skills should be exposed to the LLM.

### 3. Embedded Nanobot Architecture

- [capx-nanobot-robot-arch-plan.md](./capx-nanobot-robot-arch-plan.md)
  Describes the role of nanobot as the outer interaction shell and how it should sit above `cap-x`.

- [capx-nanobot-openarm-detailed-architecture.md](./capx-nanobot-openarm-detailed-architecture.md)
  Gives a more detailed architectural breakdown of the embedded nanobot + OpenArm stack.

## Current Reality Check

These plan files describe the intended and mostly implemented OpenArm path, but there are still some important practical limits:

- the overall `cap-x` repository still includes many GPU-oriented simulator and perception dependencies
- the OpenArm path is intentionally more CPU-oriented, but the repo as a whole is not “GPU-free”
- `capx/assets/openarm/` does not ship with calibrated real-robot motion assets out of the box
- a fresh clone still needs real-machine anchor, primitive, and combo recording before meaningful OpenArm execution

## Public Repo Notes

If you are reading this from the public fork, the safest next step is:

1. start with [docs/openarm-nanobot.md](../../docs/openarm-nanobot.md)
2. use the commands there to run `openarm_doctor`
3. only then move on to the deeper plan documents in this folder
