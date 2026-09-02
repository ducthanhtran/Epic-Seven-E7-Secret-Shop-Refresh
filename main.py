import configparser
import csv
import os
import subprocess
import sys
import threading
import time

import cv2
import keyboard
import numpy as np


CONFIG_FILE = "config.ini"
ASSETS_DIR = "assets"
ADB_PATH = os.path.join(ASSETS_DIR, "platform-tools", "adb")


class Item:
    def __init__(self, image=None, price=0, count=0):
        self.image = image
        self.price = price
        self.count = count


class Inventory:
    def __init__(self):
        self.inventory = {}

    def addItem(self, path: str, name="", price=0, count=0):
        image = cv2.imread(os.path.join("adb-assets", path))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        newItem = Item(image, price, count)
        self.inventory[name] = newItem

    def getStatusString(self):
        status_string = ""
        for key, value in self.inventory.items():
            status_string += key[0:4] + ": " + str(value.count) + " "
        return status_string

    def getName(self):
        res = []
        for key in self.inventory.keys():
            res.append(key)
        return res

    def getCount(self):
        res = []
        for value in self.inventory.values():
            res.append(value.count)
        return res

    def getTotalCost(self):
        sum = 0
        for value in self.inventory.values():
            sum += value.price * value.count
        return sum

    def writeToCSV(self, duration, skystone_spent):
        duration = round(duration, 2)

        res_folder = "ShopRefreshHistory"
        if not os.path.exists(res_folder):
            os.makedirs(res_folder)

        history_file = "ADB_History.csv"

        path = os.path.join(res_folder, history_file)
        if not os.path.isfile(path):
            with open(path, "w", newline="") as file:
                writer = csv.writer(file)
                column_name = ["Duration", "Skystone spent", "Gold spent"]
                column_name.extend(self.getName())
                writer.writerow(column_name)
        with open(path, "a", newline="") as file:
            writer = csv.writer(file)
            data = [duration, skystone_spent, self.getTotalCost()]
            data.extend(self.getCount())
            writer.writerow(data)


class ShopRefresher:
    def __init__(self, tap_sleep: float, budget: int):
        self.loop_active = False
        self.end_of_refresh = True
        self.tap_sleep = tap_sleep
        self.budget = budget
        self.stop_refresh_key = "esc"

        self.x_offset = 0
        self.y_offset = 0

        self.device_args = [] if ip_port is None else ["-s", ip_port]
        self.refresh_count = 0
        self.keyboard_thread = threading.Thread(target=self.checkKeyPress)
        self.adb_path = os.path.join("adb-assets", "platform-tools", "adb")
        self.storage = Inventory()
        self.screenwidth = 1920
        self.screenheight = 1080

        self.storage.addItem("cov.png", "Covenant bookmark", 184000)
        self.storage.addItem("mys.png", "Mystic medal", 280000)

    def start(self):
        self.loop_active = True
        self.end_of_refresh = False
        self.keyboard_thread.start()
        self.refreshShop()

    def checkKeyPress(self):
        while self.loop_active and not self.end_of_refresh:
            self.loop_active = not keyboard.is_pressed(self.stop_refresh_key)
        self.loop_active = False
        print("Shop refresh terminated!")

    def refreshShop(self):
        self.clickShop()
        # time needed for item to drop in after refresh (0.5 second loading + drop 1 second)
        sliding_time = 1.5

        start_time = time.time()
        milestone = self.budget // 10

        x1 = 0.6250 * self.screenwidth
        y1 = 0.7481 * self.screenheight
        y2 = 0.3629 * self.screenheight
        while self.loop_active:
            time.sleep(sliding_time)
            brought = set()

            if not self.loop_active:
                break
            # look at shop (page 1)
            screenshot = self.takeScreenshot()
            for key, value in self.storage.inventory.items():
                pos = self.findItemPosition(screenshot, value.image)
                if pos is not None:
                    self.clickBuy(pos)
                    value.count += 1
                    brought.add(key)

            if not self.loop_active:
                break

            # swipe

            adb_process = subprocess.run(
                [self.adb_path]
                + self.device_args
                + ["shell", "input", "swipe", str(x1), str(y1), str(x1), str(y2)]
            )
            time.sleep(1)

            if not self.loop_active:
                break
            # look at shop (page 2)
            screenshot = self.takeScreenshot()
            for key, value in self.storage.inventory.items():
                pos = self.findItemPosition(screenshot, value.image)
                if pos is not None and key not in brought:
                    self.clickBuy(pos)
                    value.count += 1

            if self.budget >= 30 and self.refresh_count * 3 >= milestone:
                sys.stdout.write(" " * 80 + "\r")
                sys.stdout.write(
                    f"{int(milestone / self.budget * 100)}% {self.storage.getStatusString()}\r"
                )
                sys.stdout.flush()
                milestone += self.budget // 10

            if not self.loop_active:
                break
            if self.budget:
                if self.refresh_count >= self.budget // 3:
                    break

            self.clickRefresh()
            self.refresh_count += 1

        self.end_of_refresh = True
        self.loop_active = False
        if self.refresh_count * 3 != self.budget:
            print("100%")
        duration = time.time() - start_time
        self.storage.writeToCSV(
            duration=duration, skystone_spent=self.refresh_count * 3
        )
        self.printResult()

    def printResult(self):
        print("\n---Result---")
        for key, value in self.storage.inventory.items():
            print(key, ":", value.count)
        print("Skystone spent:", self.refresh_count * 3)

    def takeScreenshot(self):
        adb_process = subprocess.run(
            [self.adb_path] + self.device_args + ["exec-out", "screencap", "-p"],
            stdout=subprocess.PIPE,
        )
        img_array = np.frombuffer(adb_process.stdout, dtype=np.uint8)
        screenshot = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
        return screenshot

    def findItemPosition(self, screen_image, item_image):
        result = cv2.matchTemplate(screen_image, item_image, cv2.TM_CCOEFF_NORMED)
        loc = np.where(result >= 0.75)

        if loc[0].size > 0:
            x = loc[1][0] + self.screenwidth * 0.4718
            y = loc[0][0] + self.screenheight * 0.1000
            pos = (x, y)
            return pos
        return None

    def clickShop(self):
        # newshop
        x = self.screenwidth * 0.0411
        y = self.screenheight * 0.3835
        adb_process = subprocess.run(
            [self.adb_path]
            + self.device_args
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(0.5)

        # oldshop
        x = self.screenwidth * 0.4406
        y = self.screenheight * 0.2462
        adb_process = subprocess.run(
            [self.adb_path]
            + self.device_args
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(0.5)

        # newshop
        x = self.screenwidth * 0.0411
        y = self.screenheight * 0.3835
        adb_process = subprocess.run(
            [self.adb_path]
            + self.device_args
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(0.5)

    def clickBuy(self, pos):
        if pos is None:
            return False

        x, y = pos

        adb_process = subprocess.run(
            [self.adb_path]
            + self.device_args
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(self.tap_sleep)

        # confirm
        x = self.screenwidth * 0.5677
        y = self.screenheight * 0.7037

        adb_process = subprocess.run(
            [self.adb_path]
            + self.device_args
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(self.tap_sleep)
        time.sleep(1)

    def clickRefresh(self):
        x = self.screenwidth * 0.1698
        y = self.screenheight * 0.9138

        adb_process = subprocess.run(
            [self.adb_path]
            + self.device_args
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(self.tap_sleep)

        if not self.loop_active:
            return
        # confirm
        x = self.screenwidth * 0.5828
        y = self.screenheight * 0.6411

        adb_process = subprocess.run(
            [self.adb_path]
            + self.device_args
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(self.tap_sleep)


def get_adb_devices():
    output = subprocess.check_output([ADB_PATH, "devices"], text=True)
    lines = output.splitlines()
    # Cut off first line 'List of devices attached' and last
    # empty line, thus only considering device strings
    devices = [line.split('\t')[0] for line in lines[1:-1]]
    return devices


def connect_to_device():
    output = subprocess.check_output([ADB_PATH, "connect", "localhost"], text=True)
    if "connected" in output:
        return True
    else:
        return False

def disconnect_from_device():
    subprocess.run([ADB_PATH, "disconnect"])


def get_or_create_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if not os.path.isfile(os.path.join(CONFIG_FILE)):
        print(f"{CONFIG_FILE} missing. A default file is generated")
        generate_default_config()
    config.read(CONFIG_FILE)
    print(f"Using the following config values from {CONFIG_FILE}:")
    print_config(CONFIG_FILE)
    return config

def generate_default_config() -> None:
    config = configparser.ConfigParser()
    tap_sleec_sec = float(input("Enter sleep (sec) after each tap\n"))
    skystones_budget = int(input("Enter skystones budget to be used\n"))
    config["Settings"] = {
        "tap_sleep_sec": tap_sleec_sec,
        "skystones_budget": skystones_budget
    }
    with open(CONFIG_FILE, 'w') as out:
        config.write(out)


def print_config(config_path: str) -> None:
    config = configparser.ConfigParser()
    config.read_file(open(config_path))
    for name, value in config.items('Settings'):
        print(f"\t{name}: {value}")


def main() -> None:
    if not os.path.isdir(os.path.join(ASSETS_DIR)):
        print(f"{ASSETS_DIR} folder is missing")
        sys.exit(1)

    config = get_or_create_config()

    devices = get_adb_devices()
    if len(devices) != 1:
        print("Found 0 or more than 1 ADB-devices. Exiting")
        sys.exit(2)
    
    print("Found exactly one ADB-device.")
    print(f"Trying to connect to {devices[0]}")
    if not connect_to_device():
        print("Could not connect on localhost:5555")
        sys.exit(2)
    print("Connected on localhost:5555")

    print("Use ESC to stop the refresher")
    input("Press enter to start the process...")

    sys.exit(42)

    ADBSHOP = ShopRefresher(
        tap_sleep=config.getfloat("Settings", "tap_sleep"),
        budget=config.getfloat("Settings", "budget"),
        ip_port=ip_port,
    )
    ADBSHOP.start()
    
if __name__ == "__main__":
    main()
