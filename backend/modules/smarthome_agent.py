# """
# smarthome_agent.py + ir_controller.py — MAX v4.0
# Smart Home Control:
# - IR Blaster (Broadlink RM Mini 3/Pro) for remote-only devices like Havells fan
# - Tuya WiFi devices (optional)
# - Local JSON command storage — no cloud dependency
# """
# import json
# import logging
# import base64
# from pathlib import Path
# from typing import Dict, Optional
# from config import config

# logger = logging.getLogger("MAX.SMARTHOME")

# IR_COMMANDS_FILE = Path(config.DATA_DIR) / "ir_commands.json"


# def _load_ir_commands() -> Dict[str, str]:
#     """Load saved IR hex commands."""
#     if IR_COMMANDS_FILE.exists():
#         try:
#             return json.loads(IR_COMMANDS_FILE.read_text(encoding="utf-8"))
#         except Exception:
#             pass
#     return {}


# def _save_ir_commands(cmds: Dict[str, str]):
#     IR_COMMANDS_FILE.write_text(json.dumps(cmds, indent=2, ensure_ascii=False), encoding="utf-8")


# class IRController:
#     """
#     Broadlink IR Blaster controller.
#     Controls any IR remote device (Havells fan, TV, AC, etc.)
#     Needs broadlink library: pip install broadlink
#     """

#     def __init__(self, device_ip: str = ""):
#         self.device_ip = device_ip or config.IR_BLASTER_IP
#         self._device = None

#     def _connect(self):
#         if self._device:
#             return self._device
#         try:
#             import broadlink
#             # Discover or direct connect
#             if self.device_ip:
#                 dev = broadlink.hello(self.device_ip)
#                 if isinstance(dev, list):
#                     dev = dev[0]
#                 dev.auth()
#                 self._device = dev
#                 return dev
#             else:
#                 # Auto discover
#                 devices = broadlink.discover(timeout=5)
#                 if devices:
#                     dev = devices[0]
#                     dev.auth()
#                     self._device = dev
#                     return dev
#         except Exception as e:
#             logger.error(f"IR connect failed: {e}")
#         return None

#     def learn_command(self, name: str) -> str:
#         """Learn a new IR command from remote."""
#         dev = self._connect()
#         if not dev:
#             return "IR blaster connect nahi ho paya boss. Check IP ya install broadlink."
#         try:
#             dev.enter_learning()
#             return f"Learning mode on boss! Remote se '{name}' button dabao — 10 sec mein capture karunga."
#         except Exception as e:
#             return f"Learn mode fail: {str(e)[:120]}"

#     def send_command(self, name: str) -> str:
#         """Send saved IR command."""
#         cmds = _load_ir_commands()
#         if name not in cmds:
#             available = ", ".join(cmds.keys()) if cmds else "koi bhi nahi"
#             return f"Command '{name}' saved nahi hai boss. Available: {available}. Learn karne ke liye bol."
#         dev = self._connect()
#         if not dev:
#             return "IR blaster connect nahi ho paya boss."
#         try:
#             hex_data = cmds[name]
#             # broadlink expects bytes
#             data = bytes.fromhex(hex_data)
#             dev.send_data(data)
#             return f"IR command bhej diya boss — '{name}'."
#         except Exception as e:
#             return f"IR send fail: {str(e)[:120]}"

#     def save_command(self, name: str, hex_data: str) -> str:
#         """Manually save a hex command (from external source or learning)."""
#         cmds = _load_ir_commands()
#         cmds[name] = hex_data
#         _save_ir_commands(cmds)
#         return f"Command '{name}' save ho gayi boss."


# class SmartHomeAgent:
#     """Unified smart home agent for IR + Tuya devices."""

#     def __init__(self):
#         self.ir = IRController()
#         self._tuya_device = None

#     def _get_tuya(self):
#         if self._tuya_device is None and config.TUYA_DEVICE_ID:
#             try:
#                 import tinytuya
#                 d = tinytuya.Device(config.TUYA_DEVICE_ID, config.TUYA_DEVICE_IP, config.TUYA_LOCAL_KEY)
#                 d.set_version(float(config.TUYA_DEVICE_VERSION))
#                 d.set_dpsUsed({"1": None})
#                 self._tuya_device = d
#             except Exception as e:
#                 logger.error(f"Tuya init failed: {e}")
#         return self._tuya_device

#     def fan_control(self, action: str, value: str = "") -> str:
#         """Control IR fan (Havells etc). Actions: on, off, speed1-5, swing, timer."""
#         cmd_map = {
#             "on": "fan_on",
#             "off": "fan_off",
#             "speed1": "fan_speed1",
#             "speed2": "fan_speed2",
#             "speed3": "fan_speed3",
#             "speed4": "fan_speed4",
#             "speed5": "fan_speed5",
#             "swing": "fan_swing",
#             "timer": "fan_timer",
#         }
#         cmd_name = cmd_map.get(action.lower(), f"fan_{action.lower()}")
#         return self.ir.send_command(cmd_name)

#     def light_control(self, action: str, value: str = "") -> str:
#         """Control smart light (Tuya or IR)."""
#         d = self._get_tuya()
#         if d:
#             try:
#                 d.turn_on() if action.lower() == "on" else d.turn_off()
#                 return f"Smart light {action} kar diya boss."
#             except Exception as e:
#                 return f"Light control fail: {str(e)[:120]}"
#         # Fallback IR
#         return self.ir.send_command(f"light_{action.lower()}")

#     def ac_control(self, action: str, value: str = "") -> str:
#         """Control AC (IR)."""
#         if action.lower() == "on":
#             return self.ir.send_command("ac_on")
#         elif action.lower() == "off":
#             return self.ir.send_command("ac_off")
#         elif action.lower() == "temp":
#             return self.ir.send_command(f"ac_temp_{value}")
#         return self.ir.send_command(f"ac_{action.lower()}")


# # Singleton
# _smarthome_agent: Optional[SmartHomeAgent] = None


# def get_smarthome_agent() -> SmartHomeAgent:
#     global _smarthome_agent
#     if _smarthome_agent is None:
#         _smarthome_agent = SmartHomeAgent()
#     return _smarthome_agent


# ── Stub implementations (module is disabled but main.py imports these) ──
from typing import Optional

class SmartHomeAgent:
    """Stub SmartHomeAgent — real implementation is commented out above."""

    def fan_control(self, action: str, value: str = "") -> str:
        return "Smart home module is currently disabled."

    def light_control(self, action: str, value: str = "") -> str:
        return "Smart home module is currently disabled."

    def ac_control(self, action: str, value: str = "") -> str:
        return "Smart home module is currently disabled."


_smarthome_agent: Optional[SmartHomeAgent] = None


def get_smarthome_agent() -> SmartHomeAgent:
    global _smarthome_agent
    if _smarthome_agent is None:
        _smarthome_agent = SmartHomeAgent()
    return _smarthome_agent
