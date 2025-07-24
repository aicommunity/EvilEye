from typing import List
import onnxruntime as ort
import numpy as np
import cv2
import albumentations as A
from albumentations.pytorch import ToTensorV2
from object_tracker.trackers.track_encoder import TrackEncoder


class OnnxEncoder(TrackEncoder):
    def __init__(self, model_path: str, batch_size: int = 1):
        self.batch_size = batch_size
        self.session = ort.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.image_augmentation = A.Compose(
            [A.Resize(256, 128), A.Normalize(), ToTensorV2()]
        )

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
    
