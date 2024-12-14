import sys
sys.path.append("..")
import time
import requests
import base64
import json
import cv2
import numpy as np
from PIL import Image
from flatbuffers import util
from SmartCamera import settings, ObjectDetectionTop, BoundingBox, BoundingBox2d
import pprint
import RPi.GPIO as GPIO
import spidev
from st7789 import ST7789

DEVICE_ID = settings.DEVICE_ID
CLIENT_ID = settings.CLIENT_ID
CLIENT_SECRET = settings.CLIENT_SECRET
numberofclass = settings.numberofclass
objclass = settings.objclass
access_token = settings.access_token

#Line Notifyの設定
url = "https://notify-api.line.me/api/notify"
headers = {'Authorization': 'Bearer ' + settings.access_token}

# AITRIOSのAPI関連設定
BASE_URL = "https://console.aitrios.sony-semicon.com/api/v1"
PORTAL_URL = "https://auth.aitrios.sony-semicon.com/oauth2/default/v1/token"

# グローバル変数としてアクセストークンとその有効期限を保存
ACCESS_TOKEN = None
TOKEN_EXPIRY = 0

# ラベルに関する初期化
label1 = ""
detected = ""
for i in range(numberofclass):
	print ("Class",i,"=",objclass[i])

# TFTの初期設定
image2 = np.ones((320, 480, 3), np.uint8) * 255
disp = ST7789(
	port=0,
	cs=0,
	dc=23,
	backlight=24,
	rst=25,
	width=480,
	height=	320,
	rotation=0,
	invert=False,
	spi_speed_hz=4000000
)
disp.begin()

# APIのAccess tokenの取得
def get_access_token():
    global ACCESS_TOKEN, TOKEN_EXPIRY
    current_time = time.time()
    # トークンが存在せず、または有効期限が切れている場合、新しいトークンを取得
    if ACCESS_TOKEN is None or current_time >= TOKEN_EXPIRY:
        auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "system"
        }
        response = requests.post(PORTAL_URL, headers=headers, data=data)
        if response.status_code == 200:
            token_data = response.json()
            ACCESS_TOKEN = token_data["access_token"]
            # トークンの有効期限を設定（念のため10秒早めに期限切れとする）
            TOKEN_EXPIRY = current_time + token_data.get("expires_in", 3600) - 10
        else:
            raise Exception("Failed to obtain access token")
    return ACCESS_TOKEN

# 推論結果の取得
def get_inference_results(device_id, number_of_inference_results=5):
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}/devices/{device_id}/inferenceresults"
    params = {
        "NumberOfInferenceresults": number_of_inference_results,
        "raw": 1,
        "order_by": "DESC"
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

# 画像が保管されている場所の取得
def get_image_directories(device_id):
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}/devices/images/directories"
    params = {"device_id": device_id}
    response = requests.get(url, headers=headers, params=params)
    print("response=",response.status_code)
    return response.json()

# 画像の取得
def get_images(device_id, sub_directory_name, file_name):
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}/devices/{device_id}/images/directories/{sub_directory_name}"
    params = {"order_by": "DESC"}
    response = requests.get(url, headers=headers, params=params)
    return response.json()

# 画像情報の展開
def download_image(image_data):
    image_bytes = base64.b64decode(image_data)
    nparr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

# エンコードされているデータのデコード
def decode_base64(encoded_data):
    return base64.b64decode(encoded_data)

# flatbufferでデシリアライズ
def deserialize_flatbuffers(buf):
    obj = ObjectDetectionTop.ObjectDetectionTop.GetRootAsObjectDetectionTop(buf, 0)
    perception = obj.Perception()
    results = []
    for i in range(perception.ObjectDetectionListLength()):
        detection = perception.ObjectDetectionList(i)
        if detection.BoundingBoxType() == BoundingBox.BoundingBox.BoundingBox2d:
            bbox = BoundingBox2d.BoundingBox2d()
            bbox.Init(detection.BoundingBox().Bytes, detection.BoundingBox().Pos)
            results.append({
                "class_id": detection.ClassId(),
                "score": detection.Score(),
                "left": bbox.Left(),
                "top": bbox.Top(),
                "right": bbox.Right(),
                "bottom": bbox.Bottom()
            })
    return results

# バウンディングボックスの描画
def draw_bounding_boxes(image, detections, scale_x, scale_y):
	global label1, objclass, detected
	for det in detections:
		left, top, right, bottom = int(det['left'] * scale_x), int(det['top'] * scale_y), int(det['right'] * scale_x), int(det['bottom'] * scale_y)
		cv2.rectangle(image, (left, top), (right, bottom), (0, 255, 0), 2)
		label = f"Class: {objclass[det['class_id']]}, Score: {det['score']:.2f}"
		label1 = label
		detected = objclass[det['class_id']]
		cv2.putText(image, label, (left+2, top+20), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 0), 1)
	return image

# TFTに画像を表示
def display_image_on_tft(image):
	global disp
	# 白の背景画像(キャンパス）の作成
	global image2
	image3 = np.ones((160, 320, 3), np.uint8) * 128
	print("label1=",label1,"now=",time.ctime())
	cv2.putText(image3, label1, (0, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
	cv2.putText(image3, time.ctime(), (0, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
	if (detected == "BEAR"):
	    cv2.putText(image3, "DANGER!!", (90, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255, 0),2) 
	image3=cv2.rotate(image3, cv2.ROTATE_90_CLOCKWISE)
	image3=cv2.flip(image3, 1)
	image2[0:320,0:160] = image3
	#上記の画像を反時計回りに90度回転
	image=cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
	image=cv2.flip(image, 1)
	#キャンパスに下詰でイメージをはめ込み
	image2[0:320,160:480] = image
	image = Image.fromarray(image2)
	# 画像の表示
	disp.display(image)

#以下メインプログラム
while(1):
    # 画像ディレクトリの取得
    directories = get_image_directories(DEVICE_ID)
    if not directories or not directories[0]['devices']:
        print("No image directories found")

    # 最新の1つの画像サブディレクトリ名を取得
    latest_subdirs = directories[0]['devices'][0]['Image'][-1:]

    for i, subdir in enumerate(reversed(latest_subdirs)):
        # 推論結果の取得
        inference_results = get_inference_results(DEVICE_ID, number_of_inference_results=1)
#        pprint.pprint(inference_results)

        if isinstance(inference_results, list) and len(inference_results) > 0:
            inference_data = inference_results[0]['inference_result']
            if "Inferences" in inference_data and len(inference_data["Inferences"]) > 0:
                inference = inference_data["Inferences"][0]
                if "O" in inference:
                    # メタデータのデコードとデシリアライズ
                    decoded_data = decode_base64(inference["O"])
                    deserialized_data = deserialize_flatbuffers(decoded_data)
                    imgfile = inference["T"]+".jpg"
#                    print("T: ",imgfile)

                    # スケールファクターの計算
                    scale_x = 1
                    scale_y = 1
                    image = np.ones((320, 320, 3), np.uint8) * 255
                    image_data = get_images(DEVICE_ID, subdir, imgfile)
                    imageName = image_data['images'][0]["name"]
#                    print("imageName:", imageName)
                    if (imageName == imgfile): #最新イメージと推論結果に指定されている名前が一致していたら
                        image = download_image(image_data['images'][0]["contents"])
                    # バウンディングボックスの描画
                        image_with_boxes = draw_bounding_boxes(image, deserialized_data, scale_x, scale_y)
                        # 画像の表示
                        display_image_on_tft(image_with_boxes)
	                #画像をjpegで保存
                        cv2.imwrite('jpeg.jpg', image)
        	        #Lineへメッセージ
                        message = '【熊出没注意！！】 LINE送信のテスト'
                        payload = {'message': message}
                        files = {'imageFile': open('jpeg.jpg', 'rb')}
                        if (detected == "BEAR"):
                            r = requests.post(url, headers=headers, params=payload, files=files,)
                            pprint.pprint(r)
                        detected = ""
                    else:
                        print("ReLoad!!")
                else:
                    print(f"No 'O' key in inference data for subdirectory: {subdir}")
            else:
                print(f"No inference data found for subdirectory: {subdir}")
        else:
            print(f"No response or empty response from GetInferenceResults for subdirectory: {subdir}")

