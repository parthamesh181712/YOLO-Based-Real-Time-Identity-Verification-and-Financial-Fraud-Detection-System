from ultralytics import YOLO
import cv2

model = YOLO("yolov8n.pt")
model.fuse()


def detect_faces_and_persons(image_path):
    results = model(image_path)

    persons = 0
    confidences = []

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])

            if cls == 0:
                persons += 1
                confidences.append(round(conf, 2))

    return persons, confidences