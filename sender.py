import os
import time
import argparse
import requests
import cv2

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rtsp", required=True, help="RTSP URL, ví dụ rtsp://192.168.144.25:8554/main.264")
    parser.add_argument("--server", required=True, help="Render base URL, ví dụ https://uav-relay.onrender.com")
    parser.add_argument("--stream-id", required=True, help="Tên stream, ví dụ siyi-a8")
    parser.add_argument("--token", required=True, help="Upload token khớp với Render")
    parser.add_argument("--fps", type=float, default=8.0, help="FPS gửi lên server")
    parser.add_argument("--jpeg-quality", type=int, default=75, help="JPEG quality 1-100")
    parser.add_argument("--width", type=int, default=960, help="Resize width, 0 để giữ nguyên")
    parser.add_argument("--show", action="store_true", help="Hiện preview local")
    args = parser.parse_args()

    upload_url = f"{args.server.rstrip('/')}/api/upload/{args.stream_id}"

    print(f"[INFO] Opening RTSP: {args.rtsp}")
    cap = cv2.VideoCapture(args.rtsp, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        print("[ERROR] Cannot open RTSP stream")
        return

    interval = 1.0 / max(args.fps, 0.1)
    last_sent = 0.0

    session = requests.Session()
    headers = {"X-Upload-Token": args.token}

    fail_count = 0

    while True:
        ret, frame = cap.read()

        if not ret or frame is None:
            fail_count += 1
            print(f"[WARN] Failed to read frame from RTSP (count={fail_count})")
            time.sleep(1.0)

            if fail_count >= 5:
                print("[INFO] Reconnecting RTSP...")
                cap.release()
                time.sleep(2.0)
                cap = cv2.VideoCapture(args.rtsp, cv2.CAP_FFMPEG)
                fail_count = 0
            continue

        fail_count = 0

        # resize để giảm băng thông
        if args.width > 0:
            h, w = frame.shape[:2]
            if w > args.width:
                new_h = int(h * args.width / w)
                frame = cv2.resize(frame, (args.width, new_h))

        now = time.time()
        if now - last_sent < interval:
            if args.show:
                cv2.imshow("sender-preview", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            continue

        ok, buffer = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), args.jpeg_quality]
        )

        if not ok:
            print("[WARN] JPEG encode failed")
            continue

        try:
            resp = session.post(
                upload_url,
                data=buffer.tobytes(),
                headers=headers,
                timeout=10
            )
            if resp.status_code != 200:
                print(f"[WARN] Upload failed: {resp.status_code} {resp.text}")
            else:
                print("[INFO] frame uploaded")
                last_sent = now
        except Exception as e:
            print(f"[WARN] Upload error: {e}")
            time.sleep(1.0)

        if args.show:
            cv2.imshow("sender-preview", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    if args.show:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()