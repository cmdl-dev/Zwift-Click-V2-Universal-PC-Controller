import asyncio
import threading
import time
from collections import defaultdict

import customtkinter as ctk

from bikebridge import Scanner, KeyMapper, Controller
from bikebridge.devices import DeviceRegistry, ButtonEvent, BaseDevice
from bikebridge.scanner import DiscoveredDevice

# --- Constants ---

KEYSYM_TO_PYAUTOGUI = {
    "Return": "enter", "Escape": "escape", "space": "space",
    "Left": "left", "Right": "right", "Up": "up", "Down": "down",
    "BackSpace": "backspace", "Tab": "tab", "Delete": "delete",
}

IGNORE_KEYSYMS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R",
    "Alt_L", "Alt_R", "Caps_Lock", "Num_Lock",
}

BUTTON_GROUPS = {
    "Zwift Ride": [
        ("D-Pad", ["up", "down", "left", "right"]),
        ("Face Buttons", ["a", "b", "y", "z"]),
        ("Left Side", ["shift_up_l", "shift_dn_l", "powerup_l", "onoff_l"]),
        ("Right Side", ["shift_up_r", "shift_dn_r", "powerup_r", "onoff_r"]),
    ],
    "Zwift Click v2": [
        ("Buttons", ["plus", "minus", "up", "down", "left", "right"]),
    ],
}


def normalize_key(keysym: str) -> str:
    return KEYSYM_TO_PYAUTOGUI.get(keysym, keysym.lower())


# --- Async Bridge ---

class BLEThread:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


# --- Key Capture Dialog ---

class KeyCaptureDialog(ctk.CTkToplevel):
    def __init__(self, parent, button_id: str, button_label: str, on_key, on_clear):
        super().__init__(parent)
        self.title("Remap Button")
        self.geometry("320x160")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._button_id = button_id
        self._on_key = on_key
        self._on_clear = on_clear

        ctk.CTkLabel(
            self, text=f"Press a key for:", font=ctk.CTkFont(size=13),
        ).pack(pady=(20, 2))
        ctk.CTkLabel(
            self, text=button_label, font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(0, 15))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack()
        ctk.CTkButton(
            btn_frame, text="Clear", width=90, fg_color="gray30", hover_color="gray40",
            command=self._clear,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="Cancel", width=90, fg_color="gray30", hover_color="gray40",
            command=self.destroy,
        ).pack(side="left", padx=5)

        self.bind("<KeyPress>", self._on_keypress)
        self.after(50, self.focus_force)

    def _on_keypress(self, event):
        if event.keysym in IGNORE_KEYSYMS:
            return
        key = normalize_key(event.keysym)
        self._on_key(self._button_id, key)
        self.destroy()

    def _clear(self):
        self._on_clear(self._button_id)
        self.destroy()


# --- Connect Screen ---

class ConnectFrame(ctk.CTkFrame):
    def __init__(self, master, ble_thread: BLEThread, on_connect):
        super().__init__(master, fg_color="transparent")
        self._ble = ble_thread
        self._on_connect = on_connect
        self._groups: dict[str, list[tuple[DiscoveredDevice, type[BaseDevice]]]] = defaultdict(list)
        self._scanning = False
        self._device_widgets: dict[str, ctk.CTkFrame] = {}

        # Title area
        self._title_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._title_frame.pack(expand=True)

        ctk.CTkLabel(
            self._title_frame, text="OpenBridge",
            font=ctk.CTkFont(size=32, weight="bold"),
        ).pack(pady=(0, 5))
        ctk.CTkLabel(
            self._title_frame, text="BLE Controller Key Mapper",
            font=ctk.CTkFont(size=14), text_color="gray60",
        ).pack(pady=(0, 30))

        self._connect_btn = ctk.CTkButton(
            self._title_frame, text="Connect Device", width=220, height=45,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._start_scan,
        )
        self._connect_btn.pack(pady=(0, 15))

        self._progress = ctk.CTkProgressBar(self._title_frame, width=250)
        self._progress.configure(mode="indeterminate")

        self._status_label = ctk.CTkLabel(
            self._title_frame, text="", font=ctk.CTkFont(size=13), text_color="gray60",
        )

        self._device_list = ctk.CTkScrollableFrame(
            self._title_frame, width=400, height=150, fg_color="gray14",
        )

        self._cancel_btn = ctk.CTkButton(
            self._title_frame, text="Cancel", width=120,
            fg_color="gray30", hover_color="gray40",
            command=self._cancel_scan,
        )

    def _start_scan(self):
        self._scanning = True
        self._groups.clear()
        self._device_widgets.clear()

        self._connect_btn.pack_forget()

        self._status_label.configure(text="Scanning for controllers...")
        self._status_label.pack(pady=(0, 10))
        self._progress.pack(pady=(0, 15))
        self._progress.start()
        self._device_list.pack(pady=(0, 10))
        self._cancel_btn.pack(pady=(0, 10))

        # Clear device list
        for w in self._device_list.winfo_children():
            w.destroy()

        self._ble.run(self._scan())

    async def _scan(self):
        scanner = Scanner()

        def on_found(dev: DiscoveredDevice):
            if not self._scanning:
                return
            driver = DeviceRegistry.identify(dev)
            if driver:
                self.after(0, lambda d=dev, dr=driver: self._add_device(d, dr))

        await scanner.scan_with_callback(on_found, timeout=12)

        if self._scanning:
            self.after(0, self._scan_complete)

    def _add_device(self, dev: DiscoveredDevice, driver: type[BaseDevice]):
        label = driver.DEVICE_LABEL
        self._groups[label].append((dev, driver))
        count = len(self._groups[label])

        if label in self._device_widgets:
            # Update existing row
            row = self._device_widgets[label]
            for w in row.winfo_children():
                if isinstance(w, ctk.CTkLabel):
                    radio_text = f" ({count} radios)" if count > 1 else ""
                    w.configure(text=f"{label}{radio_text}")
                    break
        else:
            row = ctk.CTkFrame(self._device_list, fg_color="gray20", corner_radius=8)
            row.pack(fill="x", pady=3, padx=5)

            ctk.CTkLabel(
                row, text=label, font=ctk.CTkFont(size=14),
            ).pack(side="left", padx=15, pady=10)

            ctk.CTkButton(
                row, text="Connect", width=90,
                command=lambda l=label: self._connect_device(l),
            ).pack(side="right", padx=15, pady=10)

            self._device_widgets[label] = row

    def _scan_complete(self):
        self._scanning = False
        self._progress.stop()
        self._progress.pack_forget()
        self._cancel_btn.pack_forget()

        if not self._groups:
            self._status_label.configure(text="No supported controllers found.")
            retry_btn = ctk.CTkButton(
                self._title_frame, text="Retry", width=120,
                command=self._reset_and_scan,
            )
            retry_btn.pack(pady=(0, 10))
        elif len(self._groups) == 1:
            label = list(self._groups.keys())[0]
            self._status_label.configure(text=f"Found {label}, connecting...")
            self.after(300, lambda: self._connect_device(label))
        else:
            self._status_label.configure(text="Select a controller:")

    def _reset_and_scan(self):
        # Clear everything and restart
        for w in self._title_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._title_frame, text="OpenBridge",
            font=ctk.CTkFont(size=32, weight="bold"),
        ).pack(pady=(0, 5))
        ctk.CTkLabel(
            self._title_frame, text="BLE Controller Key Mapper",
            font=ctk.CTkFont(size=14), text_color="gray60",
        ).pack(pady=(0, 30))

        self._status_label = ctk.CTkLabel(
            self._title_frame, text="", font=ctk.CTkFont(size=13), text_color="gray60",
        )
        self._progress = ctk.CTkProgressBar(self._title_frame, width=250)
        self._progress.configure(mode="indeterminate")
        self._device_list = ctk.CTkScrollableFrame(
            self._title_frame, width=400, height=150, fg_color="gray14",
        )
        self._cancel_btn = ctk.CTkButton(
            self._title_frame, text="Cancel", width=120,
            fg_color="gray30", hover_color="gray40",
            command=self._cancel_scan,
        )
        self._device_widgets.clear()
        self._start_scan()

    def _cancel_scan(self):
        self._scanning = False
        self._progress.stop()

        # Reset to initial state
        self._progress.pack_forget()
        self._status_label.pack_forget()
        self._device_list.pack_forget()
        self._cancel_btn.pack_forget()
        self._connect_btn.pack(pady=(0, 15))

    def _connect_device(self, label: str):
        members = self._groups[label]
        driver_cls = members[0][1]
        device_instances = [driver_cls(d.address) for d, _ in members]

        config_path = KeyMapper.default_config_path()
        mapper = KeyMapper.load(config_path)

        if not mapper.mapping:
            for btn_id, (btn_label, key) in driver_cls.default_button_map().items():
                mapper.set(btn_id, key, btn_label)
            mapper.save(config_path)

        self._on_connect(driver_cls, device_instances, mapper)


# --- Controller Screen ---

class ControllerFrame(ctk.CTkFrame):
    def __init__(
        self, master, ble_thread: BLEThread,
        driver_cls: type[BaseDevice], devices: list[BaseDevice],
        mapper: KeyMapper, on_disconnect,
    ):
        super().__init__(master, fg_color="transparent")
        self._ble = ble_thread
        self._driver_cls = driver_cls
        self._devices = devices
        self._mapper = mapper
        self._on_disconnect = on_disconnect
        self._controller: Controller | None = None
        self._config_path = KeyMapper.default_config_path()

        # Button widgets for tester highlighting
        self._tester_buttons: dict[str, ctk.CTkLabel] = {}
        # Key label widgets for mapper updating
        self._key_buttons: dict[str, ctk.CTkButton] = {}

        self._build_top_bar()
        self._build_body()
        self._start_controller()

    def _build_top_bar(self):
        bar = ctk.CTkFrame(self, height=50, fg_color="gray17", corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        ctk.CTkButton(
            bar, text="< Disconnect", width=120,
            fg_color="gray30", hover_color="gray40",
            command=self._disconnect,
        ).pack(side="left", padx=15, pady=10)

        ctk.CTkLabel(
            bar, text=self._driver_cls.DEVICE_LABEL,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left", padx=20, pady=10)

        # Battery (right side)
        self._battery_frame = ctk.CTkFrame(bar, fg_color="transparent")
        self._battery_frame.pack(side="right", padx=15, pady=10)

        self._battery_label = ctk.CTkLabel(
            self._battery_frame, text="Battery: --",
            font=ctk.CTkFont(size=13), text_color="gray60",
        )
        self._battery_label.pack(side="left", padx=(0, 8))

        self._battery_bar = ctk.CTkProgressBar(self._battery_frame, width=80, height=12)
        self._battery_bar.set(0)
        self._battery_bar.pack(side="left")

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.columnconfigure(0, weight=55)
        body.columnconfigure(1, weight=45)
        body.rowconfigure(0, weight=1)

        self._build_mapper(body)
        self._build_tester(body)

    def _build_mapper(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="gray14", corner_radius=10)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(
            frame, text="Button Mapping",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(pady=(12, 5))

        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        groups = BUTTON_GROUPS.get(self._driver_cls.DEVICE_LABEL)
        if not groups:
            groups = [("Buttons", list(self._driver_cls.default_button_map().keys()))]

        default_map = self._driver_cls.default_button_map()

        for group_name, button_ids in groups:
            ctk.CTkLabel(
                scroll, text=group_name,
                font=ctk.CTkFont(size=13, weight="bold"), text_color="gray50",
            ).pack(anchor="w", padx=10, pady=(10, 3))

            for btn_id in button_ids:
                label, _default_key = default_map.get(btn_id, (btn_id, ""))
                current_key = self._mapper.get_key(btn_id) or ""

                row = ctk.CTkFrame(scroll, fg_color="gray20", corner_radius=6, height=36)
                row.pack(fill="x", padx=5, pady=2)
                row.pack_propagate(False)

                ctk.CTkLabel(
                    row, text=label, font=ctk.CTkFont(size=13),
                ).pack(side="left", padx=12, pady=4)

                key_btn = ctk.CTkButton(
                    row, text=current_key or "(none)", width=80,
                    font=ctk.CTkFont(size=12),
                    fg_color="gray30", hover_color="gray40",
                    command=lambda bid=btn_id, lbl=label: self._open_remap(bid, lbl),
                )
                key_btn.pack(side="right", padx=12, pady=4)
                self._key_buttons[btn_id] = key_btn

    def _build_tester(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="gray14", corner_radius=10)
        frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        ctk.CTkLabel(
            frame, text="Button Tester",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(pady=(12, 8))

        # Button grid
        grid_frame = ctk.CTkFrame(frame, fg_color="transparent")
        grid_frame.pack(padx=10, pady=(0, 5))

        groups = BUTTON_GROUPS.get(self._driver_cls.DEVICE_LABEL)
        if not groups:
            groups = [("Buttons", list(self._driver_cls.default_button_map().keys()))]

        default_map = self._driver_cls.default_button_map()
        col = 0

        for group_name, button_ids in groups:
            group_frame = ctk.CTkFrame(grid_frame, fg_color="transparent")
            group_frame.grid(row=0, column=col, padx=5, pady=2, sticky="n")

            ctk.CTkLabel(
                group_frame, text=group_name,
                font=ctk.CTkFont(size=10), text_color="gray50",
            ).pack(pady=(0, 3))

            for btn_id in button_ids:
                label, _ = default_map.get(btn_id, (btn_id, ""))
                short = label.replace("Shift ", "").replace("PowerUp ", "PU ").replace("On/Off ", "")
                btn_label = ctk.CTkLabel(
                    group_frame, text=short, width=75, height=28,
                    font=ctk.CTkFont(size=11),
                    fg_color="gray25", corner_radius=5,
                )
                btn_label.pack(pady=1)
                self._tester_buttons[btn_id] = btn_label

            col += 1

        # Last pressed
        self._last_label = ctk.CTkLabel(
            frame, text="Press a button on your controller...",
            font=ctk.CTkFont(size=13), text_color="gray50",
        )
        self._last_label.pack(pady=(10, 5))

        # Event log
        ctk.CTkLabel(
            frame, text="Event Log",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="gray50",
        ).pack(anchor="w", padx=15, pady=(5, 2))

        self._event_log = ctk.CTkTextbox(
            frame, height=180, fg_color="gray10",
            font=ctk.CTkFont(size=12, family="Consolas"),
            state="disabled",
        )
        self._event_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _start_controller(self):
        for dev in self._devices:
            dev.on_battery(lambda lvl: self.after(0, lambda l=lvl: self._update_battery(l)))

        self._controller = Controller(self._devices, self._mapper)
        self._controller.on_event(
            lambda evt, key: self.after(0, lambda e=evt, k=key: self._on_button_event(e, k))
        )

        future = self._ble.run(self._controller.start())
        future.add_done_callback(lambda f: self._check_connect_error(f))

    def _check_connect_error(self, future):
        try:
            future.result(timeout=0)
        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))

    def _show_error(self, msg):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Connection Error")
        dialog.geometry("350x130")
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text=msg, wraplength=300).pack(pady=(20, 10))
        ctk.CTkButton(dialog, text="OK", width=80, command=lambda: (dialog.destroy(), self._on_disconnect())).pack()

    def _on_button_event(self, event: ButtonEvent, key: str | None):
        # Highlight tester button
        widget = self._tester_buttons.get(event.button_id)
        if widget:
            widget.configure(fg_color="#2fa572")
            self.after(300, lambda w=widget: w.configure(fg_color="gray25"))

        # Update last pressed
        key_text = key.upper() if key else "(unmapped)"
        self._last_label.configure(
            text=f"{event.button_name}  ->  {key_text}",
            text_color="white",
        )

        # Event log
        log_line = f"> {event.button_name} -> {key}" if key else f"> {event.button_name} (unmapped)"
        self._event_log.configure(state="normal")
        self._event_log.insert("0.0", log_line + "\n")
        # Cap at 50 lines
        content = self._event_log.get("1.0", "end")
        lines = content.split("\n")
        if len(lines) > 52:
            self._event_log.delete(f"{51}.0", "end")
        self._event_log.configure(state="disabled")

    def _update_battery(self, level: int):
        self._battery_label.configure(text=f"Battery: {level}%")
        self._battery_bar.set(level / 100)

    def _open_remap(self, button_id: str, button_label: str):
        if self._controller:
            self._controller.send_keys = False

        def on_key(bid, key):
            self._mapper.set(bid, key, button_label)
            self._mapper.save(self._config_path)
            btn = self._key_buttons.get(bid)
            if btn:
                btn.configure(text=key)
            if self._controller:
                self._controller.send_keys = True

        def on_clear(bid):
            self._mapper.remove(bid)
            self._mapper.save(self._config_path)
            btn = self._key_buttons.get(bid)
            if btn:
                btn.configure(text="(none)")
            if self._controller:
                self._controller.send_keys = True

        dialog = KeyCaptureDialog(self, button_id, button_label, on_key, on_clear)
        dialog.protocol("WM_DELETE_WINDOW", lambda: (
            setattr(self._controller, 'send_keys', True) if self._controller else None,
            dialog.destroy(),
        ))

    def _disconnect(self):
        if self._controller:
            self._ble.run(self._controller.stop())
        self._on_disconnect()


# --- Main App ---

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OpenBridge Controller")
        self.geometry("900x600")
        self.minsize(800, 550)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._ble = BLEThread()
        self._current_frame = None
        self.show_connect()

    def show_connect(self):
        self._clear()
        self._current_frame = ConnectFrame(self, self._ble, self._on_connected)
        self._current_frame.pack(fill="both", expand=True)

    def show_controller(self, driver_cls, devices, mapper):
        self._clear()
        self._current_frame = ControllerFrame(
            self, self._ble, driver_cls, devices, mapper, self.show_connect,
        )
        self._current_frame.pack(fill="both", expand=True)

    def _on_connected(self, driver_cls, device_instances, mapper):
        self.show_controller(driver_cls, device_instances, mapper)

    def _clear(self):
        if self._current_frame:
            self._current_frame.destroy()
            self._current_frame = None


if __name__ == "__main__":
    app = App()
    app.mainloop()
