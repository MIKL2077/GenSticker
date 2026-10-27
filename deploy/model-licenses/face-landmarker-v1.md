# MediaPipe Face Landmarker v1

Pinned public bundle (3,758,596 bytes), SHA-256:
`64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`

[Download](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task).
[Official task documentation](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker).

Google's [FaceMesh V2 model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf)
and [BlazeFace model card](https://storage.googleapis.com/mediapipe-assets/MediaPipe%20BlazeFace%20Model%20Card%20%28Short%20Range%29.pdf)
specify Apache License 2.0. MediaPipe code is Apache-2.0.
The bundle also contains a blendshape model, unused by this implementation;
[its card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf)
provides model details. Inference requests neither blendshape coefficients nor identity embeddings.

The model predicts portrait geometry, not identity. No user photo, landmark
result, or derived image is shipped with this source or retained by the model.
Downloads happen explicitly during installation, never during user generation.
