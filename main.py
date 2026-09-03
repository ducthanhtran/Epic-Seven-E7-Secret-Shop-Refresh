import configparser
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
        self.inventory: dict[str, Item] = {}

    def addItem(self, path: str, name="", price=0, count=0):
        image = cv2.imread(os.path.join("adb-assets", path))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        newItem = Item(image, price, count)
        self.inventory[name] = newItem


class Device:
    def __init__(self, tap_sleep_sec: float, swipe_sleep_sec: float, deviation_px: int):
        self.tap_sleep_sec: float = tap_sleep_sec
        self.swipe_sleep_sec: float = swipe_sleep_sec
        self.deviation_px: int = deviation_px
        self.is_connected: bool = False

    @staticmethod
    def get_adb_devices():
        output = subprocess.check_output([ADB_PATH, "devices"], text=True)
        lines = output.splitlines()
        # Cut off first line 'List of devices attached' and last
        # empty line, thus only considering device strings
        devices = [line.split('\t')[0] for line in lines[1:-1]]
        return devices

    def connect(self) -> bool:
        output = subprocess.check_output([ADB_PATH, "connect", "localhost"], text=True)
        if "connected" in output:
            self.is_connected = True
            return True
        else:
            self.is_connected = False
            return False
        
    def take_screenshot(self):
        output = subprocess.check_output([ADB_PATH, "exec-out", "screencap", "-p"])
        image = np.frombuffer(output, dtype=np.uint8)
        image_grayscale = cv2.imdecode(image, cv2.IMREAD_GRAYSCALE)
        return image_grayscale

    def tap(self, x: float, y: float) -> None:
        x_dev, y_dev = self._add_deviation(x, y)
        subprocess.run([ADB_PATH, "shell", "input", "tap",
                        str(x_dev), str(y_dev)])
        time.sleep(self.tap_sleep_sec)

    def swipe(self, x1: float, y1: float, x2: float, y2: float):
        x1_dev, y1_dev = self._add_deviation(x1, y1)
        x2_dev, y2_dev = self._add_deviation(x2, y2)
        subprocess.run([ADB_PATH, "shell", "input", "swipe",
                        str(x1_dev), str(y1_dev),
                        str(x2_dev), str(y2_dev)]
        )
        time.sleep(self.swipe_sleep_sec)

    def _add_deviation(self, x: float, y: float) -> tuple[float, float]:
        x_dev = x + np.random.normal(0, self.deviation_px)
        y_dev = y + np.random.normal(0, self.deviation_px)
        return (x_dev, y_dev)


class ShopRefresher:
    def __init__(self, tap_sleep: float, budget: int, device: Device):
        self.loop_active = False
        self.end_of_refresh = True
        self.tap_sleep = tap_sleep
        self.budget = budget
        self.stop_refresh_key = "esc"

        self.x_offset = 0
        self.y_offset = 0
        self.refresh_count = 0
        self.keyboard_thread = threading.Thread(target=self.checkKeyPress)
        self.adb_path = os.path.join("adb-assets", "platform-tools", "adb")
        self.inventory = Inventory()
        self.screenwidth = 1920
        self.screenheight = 1080

        self.inventory.addItem("cov.png", "Covenant bookmark", 184000)
        self.inventory.addItem("mys.png", "Mystic medal", 280000)
        self.device: Device = device

    def start(self):
        self.loop_active = True
        self.end_of_refresh = False
        self.keyboard_thread.start()
        self.refreshShop()

    def checkKeyPress(self):
        while self.loop_active and not self.end_of_refresh:
            self.loop_active = not keyboard.is_pressed(self.stop_refresh_key)
        self.loop_active = False

    def refreshShop(self):
        self.clickShop()
        # time needed for item to drop in after refresh (0.5 second loading + drop 1 second)
        sliding_time = 1.5

        x1 = 0.6250 * self.screenwidth
        y1 = 0.7481 * self.screenheight
        y2 = 0.3629 * self.screenheight
        while self.loop_active:
            time.sleep(sliding_time)
            brought = set()

            if not self.loop_active:
                break
            # look at shop (page 1)
            screenshot = self.device.take_screenshot()
            for key, value in self.inventory.inventory.items():
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
                + ["shell", "input", "swipe", str(x1), str(y1), str(x1), str(y2)]
            )
            time.sleep(1)

            if not self.loop_active:
                break
            # look at shop (page 2)
            screenshot = self.device.take_screenshot()
            for key, value in self.inventory.inventory.items():
                pos = self.findItemPosition(screenshot, value.image)
                if pos is not None and key not in brought:
                    self.clickBuy(pos)
                    value.count += 1

            if not self.loop_active:
                break
            if self.budget:
                if self.refresh_count >= self.budget // 3:
                    break

            self.clickRefresh()
            self.refresh_count += 1

        self.end_of_refresh = True
        self.loop_active = False

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
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(0.5)

        # oldshop
        x = self.screenwidth * 0.4406
        y = self.screenheight * 0.2462
        adb_process = subprocess.run(
            [self.adb_path]
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(0.5)

        # newshop
        x = self.screenwidth * 0.0411
        y = self.screenheight * 0.3835
        adb_process = subprocess.run(
            [self.adb_path]
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(0.5)

    def clickBuy(self, pos):
        if pos is None:
            return False

        x, y = pos

        adb_process = subprocess.run(
            [self.adb_path]
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(self.tap_sleep)

        # confirm
        x = self.screenwidth * 0.5677
        y = self.screenheight * 0.7037

        adb_process = subprocess.run(
            [self.adb_path]
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(self.tap_sleep)
        time.sleep(1)

    def clickRefresh(self):
        x = self.screenwidth * 0.1698
        y = self.screenheight * 0.9138

        adb_process = subprocess.run(
            [self.adb_path]
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
            + ["shell", "input", "tap", str(x), str(y)]
        )
        time.sleep(self.tap_sleep)




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

    devices = Device.get_adb_devices()
    if len(devices) != 1:
        print("Found 0 or more than 1 ADB-devices. Exiting")
        sys.exit(2)
    
    print("Found exactly one ADB-device.")
    print(f"Trying to connect to {devices[0]}")
    tap_sleep_sec: float = config.getfloat('Settings', 'tap_sleep_sec')
    deviation_px = 3 # debug
    device = Device(tap_sleep_sec, tap_sleep_sec, deviation_px) # TODO: use unified sleep or swipe sleep as well
    if not device.connect():
        print("Could not connect on localhost:5555")
        sys.exit(2)
    print("Connected on localhost:5555")

    print("Use ESC to stop the refresher")
    input("Press enter to start the process...")

    sys.exit(42)

    ADBSHOP = ShopRefresher(
        tap_sleep=config.getfloat("Settings", "tap_sleep"),
        budget=config.getfloat("Settings", "budget"),
        device=device,
    )
    ADBSHOP.start()
    
if __name__ == "__main__":
    main()
