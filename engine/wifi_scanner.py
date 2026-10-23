import ctypes
from ctypes import wintypes

class GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', wintypes.DWORD),
        ('Data2', wintypes.WORD),
        ('Data3', wintypes.WORD),
        ('Data4', wintypes.BYTE * 8)
    ]

class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [
        ('InterfaceGuid', GUID),
        ('strInterfaceDescription', wintypes.WCHAR * 256),
        ('isState', wintypes.DWORD)
    ]

class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [
        ('dwNumberOfItems', wintypes.DWORD),
        ('dwIndex', wintypes.DWORD),
        ('InterfaceInfo', WLAN_INTERFACE_INFO * 1)
    ]

class DOT11_SSID(ctypes.Structure):
    _fields_ = [
        ('uSSIDLength', wintypes.ULONG),
        ('ucSSID', ctypes.c_char * 32)
    ]

class WLAN_ASSOCIATION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ('dot11Ssid', DOT11_SSID),
        ('dot11BssType', wintypes.DWORD),
        ('dot11Bssid', ctypes.c_ubyte * 6),
        ('dot11PhyType', wintypes.DWORD),
        ('uDot11PhyIndex', wintypes.ULONG),
        ('wlanSignalQuality', wintypes.ULONG),
        ('ulRxRate', wintypes.ULONG),
        ('ulTxRate', wintypes.ULONG)
    ]

class WLAN_CONNECTION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ('isState', wintypes.DWORD),
        ('wlanConnectionMode', wintypes.DWORD),
        ('strProfileName', wintypes.WCHAR * 256),
        ('wlanAssociationAttributes', WLAN_ASSOCIATION_ATTRIBUTES),
        ('wlanSecurityAttributes', ctypes.c_byte * 32)
    ]

class WindowsWlanScanner:
    def __init__(self):
        self.wlanapi = ctypes.windll.wlanapi
        self.handle = wintypes.HANDLE()
        self.negotiated = wintypes.DWORD()
        self.interface_guid = None
        self.interface_desc = "Unknown"
        self._init_handle()

    def _init_handle(self):
        try:
            res = self.wlanapi.WlanOpenHandle(2, None, ctypes.byref(self.negotiated), ctypes.byref(self.handle))
            if res != 0:
                print(f"[WLAN] WlanOpenHandle failed: {res}")
                return
            
            pIfList = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
            res = self.wlanapi.WlanEnumInterfaces(self.handle, None, ctypes.byref(pIfList))
            if res == 0 and pIfList.contents.dwNumberOfItems > 0:
                info = pIfList.contents.InterfaceInfo[0]
                self.interface_desc = info.strInterfaceDescription
                # Deep copy GUID struct so it survives WlanFreeMemory
                copied_guid = GUID()
                ctypes.memmove(ctypes.byref(copied_guid), ctypes.byref(info.InterfaceGuid), ctypes.sizeof(GUID))
                self.interface_guid = copied_guid
                self.wlanapi.WlanFreeMemory(pIfList)
            else:
                print(f"[WLAN] WlanEnumInterfaces returned {res}")
        except Exception as e:
            print(f"[WLAN] Init error: {e}")

    def get_connection_telemetry(self):
        """Query real-time signal quality, rates, and SSID."""
        if not self.handle or not self.interface_guid:
            self._init_handle()
            if not self.handle or not self.interface_guid:
                return None

        data_size = wintypes.DWORD()
        pData = ctypes.c_void_p()
        opcode_value_type = wintypes.DWORD()

        res = self.wlanapi.WlanQueryInterface(
            self.handle,
            ctypes.byref(self.interface_guid),
            7, # wlan_intf_opcode_current_connection
            None,
            ctypes.byref(data_size),
            ctypes.byref(pData),
            ctypes.byref(opcode_value_type)
        )

        if res == 0:
            try:
                conn = ctypes.cast(pData, ctypes.POINTER(WLAN_CONNECTION_ATTRIBUTES)).contents
                assoc = conn.wlanAssociationAttributes
                bssid = ':'.join(f'{b:02X}' for b in assoc.dot11Bssid)
                ssid = assoc.dot11Ssid.ucSSID[:assoc.dot11Ssid.uSSIDLength].decode('utf-8', errors='ignore')
                signal_quality = assoc.wlanSignalQuality
                # Calculate estimated RSSI in dBm from Signal Quality
                # 0% -> -100 dBm, 100% -> -50 dBm
                rssi_dbm = int((signal_quality / 2.0) - 100)
                
                return {
                    "ssid": ssid,
                    "bssid": bssid,
                    "signal_quality": signal_quality,
                    "rssi_dbm": rssi_dbm,
                    "rx_rate_mbps": round(assoc.ulRxRate / 1000.0, 1),
                    "tx_rate_mbps": round(assoc.ulTxRate / 1000.0, 1),
                    "adapter": self.interface_desc
                }
            finally:
                self.wlanapi.WlanFreeMemory(pData)
        return None

    def close(self):
        if self.handle:
            self.wlanapi.WlanCloseHandle(self.handle, None)
            self.handle = None
