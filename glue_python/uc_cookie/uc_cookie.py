#!/usr/local/bin/python3
# pylint: disable=C0114

import time
import logging
import os
import threading
import sys
import argparse

import json
import requests
import qrcode
from flask import Flask, send_file, render_template, jsonify


app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
LAST_STATUS = 0
stop_event = threading.Event()
if sys.platform.startswith("win32"):
    QRCODE_DIR = "qrcode.png"
else:
    QRCODE_DIR = "/uc_cookie/qrcode.png"
UC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) uc-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch"  # noqa: E501
)
NAVIGATION_START = int(time.time() * 1000)


def get_dt():
    """
    模拟生成 dt 参数
    """
    return str(int(time.time() * 1000) - NAVIGATION_START)


def cookiejar_to_string(cookiejar):
    """
    转换 Cookie 格式
    """
    cookie_string = ""
    for cookie in cookiejar:
        cookie_string += cookie.name + "=" + cookie.value + "; "
    return cookie_string.strip('; ')


# pylint: disable=W0603
def poll_qrcode_status(stop, _token, log_print):
    """
    循环等待扫码
    """
    global LAST_STATUS
    retry_times = 0
    while not stop.is_set():
        try:
            if retry_times == 3:
                LAST_STATUS = 2
                break
            __t = int(time.time() * 1000)
            _data = {"client_id": 381, "v": 1.2, "request_id": __t, "token": _token}
            _re = requests.post(
                f"https://api.open.uc.cn/cas/ajax/getServiceTicketByQrcodeToken?__dt={get_dt()}&__t={__t}",
                data=_data,
                timeout=100,
            )
            if _re.status_code == 200:
                re_data = json.loads(_re.content)
                if re_data["status"] == 2000000:
                    logging.info("扫码成功！")
                    service_ticket = re_data["data"]["members"]["service_ticket"]
                    _re = requests.get(f"https://drive.uc.cn/account/info?st={service_ticket}", timeout=10)
                    if _re.status_code == 200:
                        uc_cookie = cookiejar_to_string(_re.cookies)
                        headers = {
                            "User-Agent": UC_UA,
                            "Referer": "https://drive.uc.cn",
                            "Cookie": uc_cookie,
                        }
                        _re = requests.get(
                            "https://pc-api.uc.cn/1/clouddrive/file/sort?pr=UCBrowser&fr=pc&pdir_fid=0&_page=1&_size=50&_fetch_total=1&_fetch_sub_dirs=0&_sort=file_type:asc,updated_at:desc",
                            headers=headers,
                            timeout=10,
                        )
                        if _re.status_code == 200:
                            uc_cookie += "; " + cookiejar_to_string(_re.cookies)
                        else:
                            logging.error("获取 __puus 失败！")
                            LAST_STATUS = 2
                            break
                        if sys.platform.startswith("win32"):
                            with open("uc_cookie.txt", "w", encoding="utf-8") as f:
                                f.write(uc_cookie)
                        else:
                            with open("/data/uc_cookie.txt", "w", encoding="utf-8") as f:
                                f.write(uc_cookie)
                        logging.info("扫码成功，UC Cookie 已写入文件！")
                    LAST_STATUS = 1
                    break
                elif re_data["status"] == 50004002:
                    logging.error("二维码无效或已过期！")
                    LAST_STATUS = 2
                    break
                elif re_data["status"] == 50004001:
                    if log_print:
                        logging.info("等待用户扫码...")
                    time.sleep(2)
        except Exception as e:  # pylint: disable=W0718
            logging.error("错误：%s", e)
            retry_times += 1


@app.route("/")
def index():
    """
    网页扫码首页
    """
    return render_template("index.html")


@app.route("/image")
def serve_image():
    """
    获取二维码图片
    """
    return send_file(QRCODE_DIR, mimetype="image/png")


@app.route("/status")
def status():
    """
    扫码状态获取
    """
    if LAST_STATUS == 1:
        return jsonify({"status": "success"})
    elif LAST_STATUS == 2:
        return jsonify({"status": "failure"})
    else:
        return jsonify({"status": "unknown"})


@app.route("/shutdown_server", methods=["GET"])
def shutdown():
    """
    退出进程
    """
    if os.path.isfile(QRCODE_DIR):
        os.remove(QRCODE_DIR)
    os._exit(0)


if __name__ == "__main__":
    if os.path.isfile(QRCODE_DIR):
        os.remove(QRCODE_DIR)
    parser = argparse.ArgumentParser(description="UC Cookie")
    parser.add_argument("--qrcode_mode", type=str, required=True, help="扫码模式")
    args = parser.parse_args()
    logging.info("二维码生成中...")
    __t = int(time.time() * 1000)
    data = {"client_id": 381, "v": 1.2, "request_id": __t}
    re = requests.post(
        f"https://api.open.uc.cn/cas/ajax/getTokenForQrcodeLogin?__dt={get_dt()}&__t={__t}",
        data=data,
        timeout=10,
    )
    if re.status_code == 200:
        token = json.loads(re.content)["data"]["members"]["token"]
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=5, border=4)
        qr.add_data(
            f"https://su.uc.cn/1_n0ZCv?uc_param_str=dsdnfrpfbivesscpgimibtbmnijblauputogpintnwktprchmt&token={token}&client_id=381&uc_biz_str=S%3Acustom%7CC%3Atitlebar_fix"
        )
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(QRCODE_DIR)
        logging.info("二维码生成完成！")
    else:
        logging.error("二维码生成失败，退出进程")
        os._exit(1)
    try:
        if args.qrcode_mode == "web":
            wait_status = threading.Thread(
                target=poll_qrcode_status,
                args=(
                    stop_event,
                    token,
                    True,
                ),
            )
            wait_status.start()
            app.run(host="0.0.0.0", port=34256)
        elif args.qrcode_mode == "shell":
            wait_status = threading.Thread(
                target=poll_qrcode_status,
                args=(
                    stop_event,
                    token,
                    False,
                ),
            )
            wait_status.start()
            logging.info("请打开 UC浏览器 APP 扫描此二维码！")
            qr.print_ascii(invert=True, tty=sys.stdout.isatty())
            while LAST_STATUS not in [1, 2]:
                time.sleep(1)
            if os.path.isfile(QRCODE_DIR):
                os.remove(QRCODE_DIR)
            if LAST_STATUS == 2:
                os._exit(1)
            os._exit(0)
        else:
            logging.error("未知的扫码模式")
            if os.path.isfile(QRCODE_DIR):
                os.remove(QRCODE_DIR)
            os._exit(1)
    except KeyboardInterrupt:
        if os.path.isfile(QRCODE_DIR):
            os.remove(QRCODE_DIR)
        stop_event.set()
        wait_status.join()
        os._exit(0)
