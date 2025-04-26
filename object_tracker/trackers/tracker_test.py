import cv2
import os
import glob
from ultralytics import YOLO
from ultralytics.engine.results import Results


def update_mot_file(frame_idx: int, results: Results):
    rows = []
    result = results[0]

    if result.boxes.id is None:
        return
    
    for i, idx in enumerate(result.boxes.id):
        x, y, w, h = result.boxes.xywh[i]
        conf = result.boxes.conf[i]
        row = f"{frame_idx} {int(idx)} {x:.2f} {y:.2f} {w:.2f} {h:.2f} {conf:.2f} -1 -1 -1\n"
        rows.append(row)
    
    with open('mot.txt', 'a') as f:
        for row in rows:
            f.write(row)


# Load the YOLOv8 model
model = YOLO('yolov8s.pt')
img_paths = glob.glob(os.path.join('test_seq', '1', '*'))

with open('mot.txt', 'w') as f:
    f.write('')

# Loop through the video frames
for i, path in enumerate(img_paths):
    # Read a frame from the video
    frame = cv2.resize(cv2.imread(path), (800, 600))

    # Run YOLOv8 tracking on the frame, persisting tracks between frames
    results = model.track(frame, conf=0.5, persist=True)

    # Visualize the results on the frame
    annotated_frame = results[0].plot()

    update_mot_file(i, results)

    # Display the annotated frame
    cv2.imshow("YOLOv8 Tracking", annotated_frame)

    # Break the loop if 'q' is pressed
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
    
# Release the video capture object and close the display window
cv2.destroyAllWindows()
