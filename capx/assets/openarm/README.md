# OpenArm Motion Assets

This directory stores manually recorded OpenArm motion assets for the `cap-x` OpenArm integration.

Layout:

- `anchors/`: named anchor poses such as `home` and `left_neutral_ready`
- `primitives/<primitive>/`: single-arm primitive templates keyed by arm, start anchor, and magnitude
- `combos/<combo>/`: editable combo templates keyed by arm mode and magnitude

Recommended workflow:

1. Record anchors first.
2. Record primitive templates from those anchors.
3. Bootstrap or record combo templates after the primitive set is stable.

Useful commands:

```bash
python -m capx.cli.openarm_assets status
python -m capx.cli.openarm_assets bootstrap-combos
python -m capx.cli.openarm_assets record-anchor left_neutral_ready --arm-mode single --arm left
python -m capx.cli.openarm_assets record-primitive left raise_upper_arm medium left_neutral_ready
```

For the full OpenArm + nanobot bringup flow, see `docs/openarm-nanobot.md`.
