from ultralytics import YOLO

model = YOLO("yolo26n.pt")

for result in model.predict(source=0, stream=True, show=True, device="mps"):
    boxes = result.boxes
    print(len(boxes), "objects")