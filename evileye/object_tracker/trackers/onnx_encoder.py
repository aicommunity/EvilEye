from typing import List
import onnxruntime as ort
import numpy as np
import cv2
import albumentations as A
from albumentations.pytorch import ToTensorV2
from .track_encoder import TrackEncoder
import os
import requests
import subprocess
import sys
from tqdm import tqdm
from ...core.logger import get_module_logger

url = "https://github.com/aicommunity/EvilEye/releases/download/dev/osnet_ain_x1_0_M.onnx"


class OnnxEncoder(TrackEncoder):
    def __init__(self, model_path: str, batch_size: int = 1):
        self.logger = get_module_logger("onnx_encoder")
        self.batch_size = batch_size

        # Resolve relative onnx path to current working directory for access
        model_path_resolved = model_path
        if not os.path.isabs(model_path_resolved):
            model_path_resolved = os.path.join(os.getcwd(), model_path_resolved)

        if not os.path.exists(model_path_resolved):
            # Create directory if it doesn't exist and path is not just filename
            dirname = os.path.dirname(model_path_resolved)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            self.logger.info(f"File not found. Downloading to {model_path_resolved}...")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            block_size = 8192

            with open(model_path_resolved, "wb") as f, tqdm(
                    total=total_size, unit='B', unit_scale=True, desc="Загрузка", ncols=80
            ) as pbar:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
            self.logger.info("Download successful")

        providers = self._select_working_providers(model_path_resolved)
        if not providers:
            raise RuntimeError(
                f"No supported ONNX Runtime execution providers are available: {ort.get_available_providers()}"
            )

        self.logger.info(
            "Initializing ONNX encoder session with providers: %s",
            providers,
        )
        self.session = ort.InferenceSession(model_path_resolved, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.image_augmentation = A.Compose(
            [A.Resize(256, 128), A.Normalize(), ToTensorV2()]
        )

    def _select_working_providers(self, model_path: str) -> list[str]:
        available = set(ort.get_available_providers())
        preferred_order = [
            "TensorrtExecutionProvider",
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]

        for provider in preferred_order:
            if provider not in available:
                continue
            if self._probe_provider_session(model_path, provider):
                return [provider]

        return ["CPUExecutionProvider"] if "CPUExecutionProvider" in available else []

    def _probe_provider_session(self, model_path: str, provider: str) -> bool:
        probe_script = (
            "import sys\n"
            "import onnxruntime as ort\n"
            "ort.InferenceSession(sys.argv[1], providers=[sys.argv[2]])\n"
            "print('ok')\n"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", probe_script, model_path, provider],
                capture_output=True,
                text=True,
                # Keep startup responsive: probing GPU providers may hang.
                timeout=4,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.logger.debug("Timed out while probing ONNX provider %s", provider)
            return False
        except Exception as e:
            self.logger.debug("Failed to probe ONNX provider %s: %s", provider, e)
            return False

        if result.returncode == 0 and "ok" in result.stdout:
            self.logger.info("Selected ONNX provider: %s", provider)
            return True

        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or f"exit_code={result.returncode}"
        self.logger.debug("ONNX provider %s is unavailable: %s", provider, details)
        return False

    def inference(self, img: np.ndarray, dets: np.ndarray) -> np.ndarray:
        """inference encoder and get features for each object

        :param img: a current frame
        :param dets: detections (Nx4) that have format [x_center. y_center, w, h]
        :return: features (NxF)
        """
        features = []

        for i in range(0, len(dets), self.batch_size):
            batch_dets = dets[i: i + self.batch_size]
            batch_crops = self._dets2crops(img, batch_dets)
            batch = self._crop2batch(batch_crops)
            output_array = self.session.run(
                [self.output_name],
                {self.input_name: batch}
            )
            features += [f for f in output_array[0]]

        features = np.array(features)
        return features

    def _dets2crops(self, img, dets) -> List[np.ndarray]:
        crops = []

        for det in dets:
            xc, yc, w, h = det[:4]
            x = xc - w / 2
            y = yc - h / 2
            x, y, w, h = map(int, [x, y, w, h])

            crop = img[y: y + h, x: x + w]
            crops.append(crop)

        return crops

    def _crop2batch(self, crops: List[np.ndarray]) -> np.ndarray:
        preprocessed_crops = [self._preprocess(c) for c in crops]
        batch = np.concatenate(preprocessed_crops, axis=0)
        return batch

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        # Assuming the model expects a 224x224 RGB image
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = self.image_augmentation(image=np.array(image))["image"]
        image = np.expand_dims(image, axis=0)
        return image
