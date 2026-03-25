# Shared Tomato Disease Model

Place the shared runtime model at `artifacts/models/tomato_disease/v1/best.pt`.

Both runtimes read the same weights file:
- ROS thin inference: `agribot_perception.thin_inference_node`
- Backend confirmation: `POST /api/v1/inference/confirm`

If you keep the model somewhere else, set `AGRIBOT_TOMATO_MODEL_PATH`.
